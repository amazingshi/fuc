import os
import sys
import shutil

from .. import api

import pandas as pd

description = f"""
This command will prepare a pipeline that converts FASTQ files to analysis-ready BAM files.

Here, "analysis-ready" means the final BAM files will be: 1) aligned to a reference genome, 2) sorted by genomic coordinate, 3) marked for duplicate reads, 4) recalibrated by BQSR model, and 5) ready for downstream analyses such as variant calling.

External dependencies:
  - SGE: Required for job submission (i.e. qsub).
  - BWA: Required for read alignment.
  - SAMtools: Required for sorting and indexing BAM files.
  - GATK: Required for marking duplicate reads and recalibrating BAM files.

Manifest columns:
  - Name: Sample name.
  - Read1: Path to forward FASTA file.
  - Read2: Path to reverse FASTA file.

Usage examples:
  $ fuc {api.common._script_name()} manifest.csv ref.fa output_dir "-q queue_name -pe pe_name 10" --thread 10
  $ fuc {api.common._script_name()} manifest.csv ref.fa output_dir "-l h='node_A|node_B' -pe pe_name 10" --thread 10
"""

def create_parser(subparsers):
    parser = api.common._add_parser(
        subparsers,
        api.common._script_name(),
        help='Pipeline for converting FASTQ files to analysis-ready BAM files.',
        description=description,
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
        'qsub1',
        type=str,
        help='Options for qsub.'
    )
    parser.add_argument(
        'qsub2',
        type=str,
        help='Options for qsub.'
    )
    parser.add_argument(
        'java',
        help='Options for Java.'
    )
    parser.add_argument(
        'vcf',
        type=str,
        nargs='+',
        help='VCF file containing known sites.'
    )
    parser.add_argument(
        '--bed',
        metavar='PATH',
        type=str,
        help='BED file.'
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
        help="Sequencing platform (default: Illumina)."
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

            f.write(
f"""#!/bin/bash

# Activate conda environment.
source activate {api.common.conda_env()}

# Get read group information.
first=`zcat {r.Read1} | head -1`
flowcell=`echo "$first" | awk -F " " '{{print $1}}' | awk -F ":" '{{print $3}}'`
barcode=`echo "$first" | awk -F " " '{{print $2}}' | awk -F ":" '{{print $4}}'`
group="@RG\\tID:$flowcell\\tPU:$flowcell.$barcode\\tSM:{r.Name}\\tPL:{args.platform}\\tLB:{r.Name}"

# Align and sort seuqnece reads. Also assign read group to mapped reads.
bwa mem -M -R $group -t {args.thread} {args.fasta} {r.Read1} {r.Read2} | samtools sort -@ {args.thread} -o {args.output}/temp/{r.Name}.sorted.bam -
""")

        with open(f'{args.output}/shell/S2-{r.Name}.sh', 'w') as f:

            ##################
            # MarkDuplicates #
            ##################

            command1 = 'gatk MarkDuplicates'
            command1 += f' --QUIET'
            command1 += f' --java-options "{args.java}"'
            command1 += f' -I {args.output}/temp/{r.Name}.sorted.bam'
            command1 += f' -O {args.output}/temp/{r.Name}.sorted.markdup.bam'
            command1 += f' -M {args.output}/temp/{r.Name}.metrics'

            ####################
            # BaseRecalibrator #
            ####################

            command2 = 'gatk BaseRecalibrator'
            command2 += f' --QUIET'
            command2 += f' --java-options "{args.java}"'
            command2 += f' -R {args.fasta}'
            command2 += f' -I {args.output}/temp/{r.Name}.sorted.markdup.bam'
            command2 += f' -O {args.output}/temp/{r.Name}.table'
            command2 += ' ' + ' '.join([f'--known-sites {x}' for x in args.vcf])

            if args.bed is not None:
                command2 += f' -L {args.bed}'

            #############
            # ApplyBQSR #
            #############

            command3 = 'gatk ApplyBQSR'
            command3 += f' --QUIET'
            command3 += f' --java-options "{args.java}"'
            command3 += f' -bqsr {args.output}/temp/{r.Name}.table'
            command3 += f' -I {args.output}/temp/{r.Name}.sorted.markdup.bam'
            command3 += f' -O {args.output}/{r.Name}.sorted.markdup.recal.bam'

            if args.bed is not None:
                command3 += f' -L {args.bed}'

            f.write(
f"""#!/bin/bash

# Activate conda environment.
source activate {api.common.conda_env()}

# Mark duplicate reads.
{command1}

# Index BAM file.
samtools index {args.output}/temp/{r.Name}.sorted.markdup.bam

# Build BQSR model.
{command2}

# Apply BQSR model.
{command3}

# Remove temporary files.
{remove} -r {args.output}/temp/*
""")

    with open(f'{args.output}/shell/qsubme.sh', 'w') as f:
        f.write(
f"""#!/bin/bash

p={args.output}

samples=({" ".join(df.Name)})

for sample in ${{samples[@]}}
do
  qsub {args.qsub1} -S /bin/bash -e $p/log -o $p/log -N S1 $p/shell/S1-$sample.sh
done

for sample in ${{samples[@]}}
do
  qsub {args.qsub2} -S /bin/bash -e $p/log -o $p/log -N S2 -hold_jid S1 $p/shell/S2-$sample.sh
done
""")
