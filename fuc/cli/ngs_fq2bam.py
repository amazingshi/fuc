import os
import sys
import shutil

from .. import api

import pandas as pd

description = f"""
Pipeline for converting FASTQ files to analysis-ready BAM files.

Here, "analysis-ready" means that the final BAM files are: 1) aligned to a
reference genome, 2) sorted by genomic coordinate, 3) marked for duplicate
reads, 4) recalibrated by BQSR model, and 5) ready for downstream analyses
such as variant calling.

External dependencies:
  - SGE: Required for job submission (i.e. qsub).
  - BWA: Required for read alignment (i.e. BWA-MEM).
  - SAMtools: Required for sorting and indexing BAM files.
  - GATK: Required for marking duplicate reads and recalibrating BAM files.

Manifest columns:
  - Name: Sample name.
  - Read1: Path to forward FASTA file.
  - Read2: Path to reverse FASTA file.
"""

epilog = f"""
[Example] Specify queue:
  $ fuc {api.common._script_name()} \\
  manifest.csv \\
  ref.fa \\
  output_dir \\
  "-q queue_name -pe pe_name 10" \\
  "-Xmx15g -Xms15g" \\
  1.vcf 2.vcf 3.vcf \\
  --thread 10

[Example] Specify nodes:
  $ fuc {api.common._script_name()} \\
  manifest.csv \\
  ref.fa \\
  output_dir \\
  "-l h='node_A|node_B' -pe pe_name 10" \\
  "-Xmx15g -Xms15g" \\
  1.vcf 2.vcf 3.vcf \\
  --thread 10
"""

def create_parser(subparsers):
    parser = api.common._add_parser(
        subparsers,
        api.common._script_name(),
        description=description,
        epilog=epilog,
        help='Pipeline for converting FASTQ files to analysis-ready BAM files.',
    )
    parser.add_argument(
        'manifest',
        help='Sample manifest CSV file.'
    )
    parser.add_argument(
        'fasta',
        help='Reference FASTA file.'
    )
    parser.add_argument(
        'output',
        type=os.path.abspath,
        help='Output directory.'
    )
    parser.add_argument(
        'qsub',
        type=str,
        help='SGE resoruce to request for qsub.'
    )
    parser.add_argument(
        'java',
        help='Java resoruce to request for GATK.'
    )
    parser.add_argument(
        'vcf',
        type=str,
        nargs='+',
        help='One or more reference VCF files containing known variant \n'
             'sites (e.g. 1000 Genomes Project).'
    )
    parser.add_argument(
        '--bed',
        metavar='PATH',
        type=str,
        help='BED file.'
    )
    parser.add_argument(
        '--thread',
        metavar='INT',
        type=int,
        default=1,
        help='Number of threads to use (default: 1).'
    )
    parser.add_argument(
        '--platform',
        metavar='TEXT',
        type=str,
        default='Illumina',
        help="Sequencing platform (default: 'Illumina')."
    )
    parser.add_argument(
        '--job',
        metavar='TEXT',
        type=str,
        help='Job submission ID for SGE.'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Overwrite the output directory if it already exists.'
    )
    parser.add_argument(
        '--keep',
        action='store_true',
        help='Keep temporary files.'
    )

def main(args):
    if os.path.exists(args.output) and args.force:
        shutil.rmtree(args.output)

    os.mkdir(args.output)
    os.mkdir(f'{args.output}/shell')
    os.mkdir(f'{args.output}/log')
    os.mkdir(f'{args.output}/temp')

    with open(f'{args.output}/command.txt', 'w') as f:
        f.write(' '.join(sys.argv) + '\n')

    df = pd.read_csv(args.manifest)

    if args.keep:
        remove = '# rm'
    else:
        remove = 'rm'

    for i, r in df.iterrows():
        with open(f'{args.output}/shell/S1-{r.Name}.sh', 'w') as f:

            ###########
            # BWA-MEM #
            ###########

            command1 = 'bwa mem'
            command1 += f' -M -R $group -t {args.thread} '
            command1 += f' {args.fasta} {r.Read1} {r.Read2} |'
            command1 += f' samtools sort -@ {args.thread}'
            command1 += f' -o {args.output}/temp/{r.Name}.sorted.bam -'

            ##################
            # MarkDuplicates #
            ##################

            command2 = 'gatk MarkDuplicates'
            command2 += f' --QUIET'
            command2 += f' --java-options "{args.java}"'
            command2 += f' -I {args.output}/temp/{r.Name}.sorted.bam'
            command2 += f' -O {args.output}/temp/{r.Name}.sorted.markdup.bam'
            command2 += f' -M {args.output}/temp/{r.Name}.metrics'

            ####################
            # BaseRecalibrator #
            ####################

            command3 = 'gatk BaseRecalibrator'
            command3 += f' --QUIET'
            command3 += f' --java-options "{args.java}"'
            command3 += f' -R {args.fasta}'
            command3 += f' -I {args.output}/temp/{r.Name}.sorted.markdup.bam'
            command3 += f' -O {args.output}/temp/{r.Name}.table'
            command3 += ' ' + ' '.join([f'--known-sites {x}' for x in args.vcf])
            if args.bed is not None:
                command3 += f' -L {args.bed}'

            #############
            # ApplyBQSR #
            #############

            command4 = 'gatk ApplyBQSR'
            command4 += f' --QUIET'
            command4 += f' --java-options "{args.java}"'
            command4 += f' -bqsr {args.output}/temp/{r.Name}.table'
            command4 += f' -I {args.output}/temp/{r.Name}.sorted.markdup.bam'
            command4 += f' -O {args.output}/{r.Name}.sorted.markdup.recal.bam'
            if args.bed is not None:
                command4 += f' -L {args.bed}'

            f.write(
f"""#!/bin/bash

# Activate conda environment.
source activate {api.common.conda_env()}

# Get read group information.
first=`zcat {r.Read1} | head -1`
flowcell=`echo "$first" | awk -F " " '{{print $1}}' | awk -F ":" '{{print $3}}'`
barcode=`echo "$first" | awk -F " " '{{print $2}}' | awk -F ":" '{{print $4}}'`
group="@RG\\tID:$flowcell\\tPU:$flowcell.$barcode\\tSM:{r.Name}\\tPL:{args.platform}\\tLB:{r.Name}"

# Align and sort seuqnece reads. Assign read group as well.
{command1}

# Mark duplicate reads.
{command2}

# Index BAM file.
samtools index {args.output}/temp/{r.Name}.sorted.markdup.bam

# Build BQSR model.
{command3}

# Apply BQSR model.
{command4}

# Remove temporary files.
{remove} {args.output}/temp/{r.Name}.metrics
{remove} {args.output}/temp/{r.Name}.table
{remove} {args.output}/temp/{r.Name}.sorted.bam
{remove} {args.output}/temp/{r.Name}.sorted.markdup.bam
{remove} {args.output}/temp/{r.Name}.sorted.markdup.bam.bai
""")

    if args.job is None:
        jid = ''
    else:
        jid = '-' + args.job

    with open(f'{args.output}/shell/qsubme.sh', 'w') as f:
        f.write(
f"""#!/bin/bash

p={args.output}

samples=({" ".join(df.Name)})

for sample in ${{samples[@]}}
do
  qsub {args.qsub} -S /bin/bash -e $p/log -o $p/log -N S1-$sample{jid} $p/shell/S1-$sample.sh
done
""")
