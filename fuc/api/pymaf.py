"""
The pymaf submodule is designed for working with MAF files. It implements
the ``pymaf.MafFrame`` class which stores MAF data as ``pandas.DataFrame``
to allow fast computation and easy manipulation. The submodule strictly
adheres to the standard `MAF specification
<https://docs.gdc.cancer.gov/Data/File_Formats/MAF_Format/>`_.
"""

import pandas as pd
import seaborn as sns
import numpy as np
import re
import matplotlib.pyplot as plt
from . import pyvcf

VARCLS_DICT = {
    "3'Flank": {'COLOR': None},
    "3'UTR": {'COLOR': None},
    "5'Flank": {'COLOR': None},
    "5'UTR": {'COLOR': None},
    'De_novo_Start_InFrame': {'COLOR': None},
    'De_novo_Start_OutOfFrame': {'COLOR': None},
    'Frame_Shift_Del': {'COLOR': 'tab:blue'},
    'Frame_Shift_Ins': {'COLOR': 'tab:purple'},
    'IGR': {'COLOR': None},
    'In_Frame_Del': {'COLOR': 'tab:olive'},
    'In_Frame_Ins': {'COLOR': 'tab:red'},
    'Intron': {'COLOR': None},
    'Missense_Mutation': {'COLOR': 'tab:green'},
    'Nonsense_Mutation': {'COLOR': 'tab:cyan'},
    'Nonstop_Mutation': {'COLOR': 'tab:pink'},
    'RNA': {'COLOR': None},
    'Silent': {'COLOR': None},
    'Splice_Region': {'COLOR': None},
    'Splice_Site': {'COLOR': 'tab:orange'},
    'Start_Codon_Ins': {'COLOR': None},
    'Start_Codon_SNP': {'COLOR': None},
    'Stop_Codon_Del': {'COLOR': None},
    'Targeted_Region': {'COLOR': None},
    'Translation_Start_Site': {'COLOR': 'tab:brown'},
    'lincRNA': {'COLOR': None},
}

NONSYN_NAMES = [
    'Missense_Mutation', 'Frame_Shift_Del', 'Frame_Shift_Ins',
    'In_Frame_Del', 'In_Frame_Ins', 'Nonsense_Mutation',
    'Nonstop_Mutation', 'Splice_Site', 'Translation_Start_Site'
]

NONSYN_COLORS = [VARCLS_DICT[x]['COLOR'] for x in NONSYN_NAMES]

SNVCLS = {
    'A>C': {'REP': 'T>G'},
    'A>G': {'REP': 'T>C'},
    'A>T': {'REP': 'T>A'},
    'C>A': {'REP': 'C>A'},
    'C>G': {'REP': 'C>G'},
    'C>T': {'REP': 'C>T'},
    'G>A': {'REP': 'C>T'},
    'G>C': {'REP': 'C>G'},
    'G>T': {'REP': 'C>A'},
    'T>A': {'REP': 'T>A'},
    'T>C': {'REP': 'T>C'},
    'T>G': {'REP': 'T>G'},
}

def vcf2maf(fn):
    """Convert a VCF file to a MAF file.

    Parameters
    ----------
    fn : str
        VCF file path.
    """
    vf = pyvcf.VcfFrame.from_file(fn)

    # Get the NCBI_Build data.
    for line in vf.meta:
        if line.startswith('##VEP'):
            ncbi_build = re.search(r'assembly="(.*?)"', line).group(1)

    # Define the conversion algorithm.
    def one_row(r):
        fields = r.INFO.replace('CSQ=', '').split(',')[0].split('|')
        strand = '+' if fields[19] == '1' else '-'

        # Get the Variant_Type data.
        if len(r.REF) == len(r.ALT) == 1:
            variant_type = 'SNP'
        elif len(r.REF) > len(r.ALT):
            variant_type = 'DEL'
        else:
            variant_type = 'INS'

        # Get the Variant_Classification data.
        consequence = fields[1].split('&')[0]
        if consequence == 'missense_variant':
            variant_classification = 'Missense_Mutation'
        elif consequence in ['splice_acceptor_variant',
            'splice_donor_variant', 'transcript_ablation']:
            variant_classification = 'Splice_Site'
        elif consequence == 'splice_region_variant':
            variant_classification = 'Splice_Region'
        elif consequence == 'stop_gained':
            variant_classification = 'Nonsense_Mutation'
        elif consequence == 'stop_lost':
            variant_classification = 'Nonstop_Mutation'
        elif consequence == 'frameshift_variant' and  variant_type == 'DEL':
            variant_classification = 'Frame_Shift_Del'
        elif consequence == 'frameshift_variant' and  variant_type == 'INS':
            variant_classification = 'Frame_Shift_Ins'
        elif consequence in ['initiator_codon_variant', 'start_lost']:
            variant_classification = 'Translation_Start_Site'
        elif consequence == 'inframe_insertion':
            variant_classification = 'In_Frame_Ins'
        elif consequence == 'inframe_deletion':
            variant_classification = 'In_Frame_Del'
        elif consequence in ['transcript_amplification', 'intron_variant']:
            variant_classification = 'Intron'
        elif consequence in ['incomplete_terminal_codon_variant',
            'synonymous_variant', 'stop_retained_variant',
            'NMD_transcript_variant']:
            variant_classification = 'Silent'
        elif consequence in ['mature_miRNA_variant',
            'non_coding_transcript_exon_variant',
            'non_coding_transcript_variant']:
            variant_classification = 'RNA'
        elif consequence == '5_prime_UTR_variant':
            variant_classification = "5'UTR"
        elif consequence == '3_prime_UTR_variant':
            variant_classification = "3'UTR"
        elif consequence in ['TF_binding_site_variant',
            'regulatory_region_variant', 'intergenic_variant']:
            variant_classification = 'IGR'
        elif consequence == 'upstream_gene_variant':
            variant_classification = "5'Flank"
        elif consequence == 'downstream_gene_variant':
            variant_classification = "3'Flank"
        else:
            raise ValueError(f'Unknown consequence found: {consequence}')

        # Get the Tumor_Sample_Barcode data.
        s = r[9:].apply(pyvcf.gt_hasvar)
        tumor_sample_barcode = ','.join(s[s].index.to_list())

        # Get the Protein_Change data.
        if fields[14]:
            pos = fields[14]
            aa = fields[15].split('/')
            protein_change = f'p.{aa[0]}{pos}{aa[1]}'
        else:
            protein_change = '.'

        d = dict(
            Hugo_Symbol = fields[3],
            Entrez_Gene_Id = fields[4],
            Center = '.',
            NCBI_Build = ncbi_build,
            Chromosome = r.CHROM,
            Start_Position = r.POS,
            End_Position = r.POS,
            Strand = strand,
            Variant_Classification = variant_classification,
            Variant_Type = variant_type,
            Reference_Allele = r.REF,
            Tumor_Seq_Allele1 = r.ALT,
            Tumor_Seq_Allele2 = r.ALT,
            Tumor_Sample_Barcode = tumor_sample_barcode,
            Protein_Change = protein_change,
        )

        return pd.Series(d)

    # Apply the conversion algorithm.
    df = vf.df.apply(one_row, axis=1)

    # Expand the Tumor_Sample_Barcode column to multiple rows.
    s = df['Tumor_Sample_Barcode'].str.split(',').apply(pd.Series, 1).stack()
    s.index = s.index.droplevel(-1)
    s.name = 'Tumor_Sample_Barcode'
    del df['Tumor_Sample_Barcode']
    df = df.join(s)

    return MafFrame(df)

class MafFrame:
    """Class for storing MAF data.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame containing MAF data.

    See Also
    --------
    MafFrame.from_file
        Construct MafFrame from a MAF file.
    """
    def __init__(self, df):
        self.df = df.reset_index(drop=True)

    @property
    def shape(self):
        """tuple : Dimensionality of MafFrame (variants, samples)."""
        return (self.df.shape[0], len(self.samples))

    @property
    def samples(self):
        """list : List of the sample names."""
        return list(self.df.Tumor_Sample_Barcode.unique())

    @property
    def genes(self):
        """list : List of the genes."""
        return list(self.df.Hugo_Symbol.unique())

    @classmethod
    def from_file(cls, fn):
        """Construct MafFrame from a MAF file.

        Parameters
        ----------
        fn : str
            MAF file path (zipped or unzipped).

        Returns
        -------
        MafFrame
            MafFrame.

        See Also
        --------
        MafFrame
            MafFrame object creation using constructor.
        """
        return cls(pd.read_table(fn))

    def plot_genes(self, count=10, ax=None, figsize=None, **kwargs):
        """Create a bar plot for mutated genes.

        Parameters
        ----------
        count : int, default: 10
            Number of top mutated genes to display.
        ax : matplotlib.axes.Axes, optional
            Pre-existing axes for the plot. Otherwise, crete a new one.
        figsize : tuple, optional
            Width, height in inches. Format: (float, float).
        kwargs
            Other keyword arguments will be passed down to
            :meth:`pandas.DataFrame.plot.barh`.

        Returns
        -------
        matplotlib.axes.Axes
            The matplotlib axes containing the plot.

        Examples
        --------

        .. plot::

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> f = '~/fuc-data/tcga-laml/tcga_laml.maf.gz'
            >>> mf = pymaf.MafFrame.from_file(f)
            >>> mf.plot_genes()
            >>> plt.tight_layout()
        """
        df = self.df[self.df.Variant_Classification.isin(NONSYN_NAMES)]
        df = df.groupby('Hugo_Symbol')[
            'Variant_Classification'].value_counts().to_frame()
        df.columns = ['Count']
        df = df.reset_index()
        df = df.pivot(index='Hugo_Symbol', columns='Variant_Classification',
            values='Count')
        df = df.fillna(0)
        for varcls in NONSYN_NAMES:
            if varcls not in df.columns:
                df[varcls] = 0
        i = df.sum(axis=1).sort_values(ascending=False).index
        df = df.reindex(index=i)
        df = df[NONSYN_NAMES]
        df = df[:count]
        df = df.iloc[::-1]
        df = df.rename_axis(None, axis=1)
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        if kwargs is None:
            kwargs = {}
        df.plot.barh(stacked=True, ax=ax, color=NONSYN_COLORS)
        ax.set_xlabel('Count')
        ax.set_ylabel('')
        return ax

    def plot_samples(self, ax=None, figsize=None, **kwargs):
        """Create a bar plot for variants per sample.

        Parameters
        ----------
        ax : matplotlib.axes.Axes, optional
            Pre-existing axes for the plot. Otherwise, crete a new one.
        figsize : tuple, optional
            Width, height in inches. Format: (float, float).
        kwargs
            Other keyword arguments will be passed down to
            :meth:`pandas.DataFrame.plot.barh`.

        Returns
        -------
        matplotlib.axes.Axes
            The matplotlib axes containing the plot.

        Examples
        --------

        .. plot::

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> f = '~/fuc-data/tcga-laml/tcga_laml.maf.gz'
            >>> mf = pymaf.MafFrame.from_file(f)
            >>> mf.plot_samples()
            >>> plt.tight_layout()
        """
        df = self.df[self.df.Variant_Classification.isin(NONSYN_NAMES)]
        df = df.groupby('Tumor_Sample_Barcode')[
            'Variant_Classification'].value_counts().to_frame()
        df.columns = ['Count']
        df = df.reset_index()
        df = df.pivot(index='Tumor_Sample_Barcode',
            columns='Variant_Classification', values='Count')
        df = df.fillna(0)
        for varcls in NONSYN_NAMES:
            if varcls not in df.columns:
                df[varcls] = 0
        i = df.sum(axis=1).sort_values(ascending=False).index
        df = df.reindex(index=i)
        df = df[NONSYN_NAMES]
        df = df.rename_axis(None, axis=1)
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        if kwargs is None:
            kwargs = {}
        df.plot.bar(stacked=True, ax=ax, width=1.0,
            color=NONSYN_COLORS, **kwargs)
        ax.set_xlabel('Samples')
        ax.set_ylabel('Count')
        ax.set_xticks([])
        return ax

    def plot_snvcls(self, ax=None, figsize=None, **kwargs):
        """Create a bar plot for SNV class.

        Parameters
        ----------
        ax : matplotlib.axes.Axes, optional
            Pre-existing axes for the plot. Otherwise, crete a new one.
        figsize : tuple, optional
            Width, height in inches. Format: (float, float).
        kwargs
            Other keyword arguments will be passed down to
            :meth:`matplotlib.axes.Axes.bar` and :meth:`seaborn.barplot`.

        Returns
        -------
        matplotlib.axes.Axes
            The matplotlib axes containing the plot.

        Examples
        --------

        .. plot::

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> f = '~/fuc-data/tcga-laml/tcga_laml.maf.gz'
            >>> mf = pymaf.MafFrame.from_file(f)
            >>> mf.plot_snvcls()
            >>> plt.tight_layout()
        """
        def one_row(r):
            ref = r.Reference_Allele
            alt = r.Tumor_Seq_Allele2
            if (ref == '-' or
                alt == '-' or
                len(alt) != 1 or
                len(ref) != 1 or
                ref == alt):
                return np.nan
            return SNVCLS[f'{ref}>{alt}']['REP']
        s = self.df.apply(one_row, axis=1).value_counts()
        i = sorted(set([v['REP'] for k, v in SNVCLS.items()]))
        s = s.reindex(index=i)
        df = s.to_frame().reset_index()
        df.columns = ['SNV', 'Count']
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        if kwargs is None:
            kwargs = {}
        sns.barplot(x='Count', y='SNV', data=df, ax=ax, **kwargs)
        ax.set_xlabel('Count')
        ax.set_ylabel('')
        return ax

    def plot_varcls(self, ax=None, figsize=None, **kwargs):
        """Create a bar plot for the nonsynonymous variant classes.

        Parameters
        ----------
        ax : matplotlib.axes.Axes, optional
            Pre-existing axes for the plot. Otherwise, crete a new one.
        figsize : tuple, optional
            Width, height in inches. Format: (float, float).
        kwargs
            Other keyword arguments will be passed down to
            :meth:`matplotlib.axes.Axes.bar` and :meth:`seaborn.barplot`.

        Returns
        -------
        matplotlib.axes.Axes
            The matplotlib axes containing the plot.

        Examples
        --------

        .. plot::

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> f = '~/fuc-data/tcga-laml/tcga_laml.maf.gz'
            >>> mf = pymaf.MafFrame.from_file(f)
            >>> mf.plot_varcls()
            >>> plt.tight_layout()
        """
        d = self.df.Variant_Classification.value_counts().to_dict()
        counts = {}
        for varcls in NONSYN_NAMES:
            if varcls in d:
                counts[varcls] = d[varcls]
            else:
                counts[varcls] = 0
        s = pd.Series(counts).reindex(index=NONSYN_NAMES)
        df = s.to_frame().reset_index()
        df.columns = ['Variant_Classification', 'Count']
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        if kwargs is None:
            kwargs = {}
        sns.barplot(x='Count', y='Variant_Classification', data=df,
                    ax=ax, palette=NONSYN_COLORS, **kwargs)
        ax.set_ylabel('')
        return ax

    def plot_vartype(self, ax=None, figsize=None, **kwargs):
        """Create a bar plot for viaration type.

        Parameters
        ----------
        ax : matplotlib.axes.Axes, optional
            Pre-existing axes for the plot. Otherwise, crete a new one.
        figsize : tuple, optional
            Width, height in inches. Format: (float, float).
        kwargs
            Other keyword arguments will be passed down to
            :meth:`matplotlib.axes.Axes.bar` and :meth:`seaborn.barplot`.

        Returns
        -------
        matplotlib.axes.Axes
            The matplotlib axes containing the plot.

        Examples
        --------

        .. plot::

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> f = '~/fuc-data/tcga-laml/tcga_laml.maf.gz'
            >>> mf = pymaf.MafFrame.from_file(f)
            >>> mf.plot_vartype()
            >>> plt.tight_layout()
        """
        s = self.df.Variant_Type.value_counts()
        df = s.to_frame().reset_index()
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        if kwargs is None:
            kwargs = {}
        sns.barplot(x='Variant_Type', y='index', data=df, ax=ax, **kwargs)
        ax.set_xlabel('Count')
        ax.set_ylabel('')
        return ax

    def plot_waterfall(self, count=10, ax=None, figsize=None, **kwargs):
        """Create a waterfall plot (oncoplot).

        Parameters
        ----------
        count : int, default: 10
            Number of top mutated genes to display.
        ax : matplotlib.axes.Axes, optional
            Pre-existing axes for the plot. Otherwise, crete a new one.
        figsize : tuple, optional
            Width, height in inches. Format: (float, float).
        kwargs
            Other keyword arguments will be passed down to
            :meth:`matplotlib.axes.Axes.pcolormesh()` and
            :meth:`seaborn.heatmap`.

        Returns
        -------
        matplotlib.axes.Axes
            The matplotlib axes containing the plot.

        Examples
        --------

        .. plot::

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> f = '~/fuc-data/tcga-laml/tcga_laml.maf.gz'
            >>> mf = pymaf.MafFrame.from_file(f)
            >>> mf.plot_waterfall(figsize=(10, 5), linewidths=0.5)
            >>> plt.tight_layout()
        """
        df = self.df[self.df.Variant_Classification.isin(NONSYN_NAMES)]
        f = lambda x: ''.join(x) if len(x) == 1 else 'Multi_Hit'
        df = df.groupby(['Hugo_Symbol', 'Tumor_Sample_Barcode'])[
            'Variant_Classification'].apply(f).to_frame()
        df = df.reset_index()
        df = df.pivot(index='Hugo_Symbol', columns='Tumor_Sample_Barcode',
            values='Variant_Classification')

        # Sort the rows (genes).
        i = df.isnull().sum(axis=1).sort_values(ascending=True).index
        df = df.reindex(index=i)

        # Select the top mutated genes.
        df = df[:count]

        # Remove columns (samples) with all NaN's.
        df = df.dropna(axis=1, how='all')

        # Sort the columns (samples).
        c = df.applymap(lambda x: 0 if pd.isnull(x) else 1).sort_values(
            df.index.to_list(), axis=1, ascending=False).columns
        df = df[c]

        # Apply the mapping between items and integers.
        df = df.fillna('None')
        l = reversed(NONSYN_NAMES + ['Multi_Hit', 'None'])
        d = {k: v for v, k in enumerate(l)}
        df = df.applymap(lambda x: d[x])

        # Plot the heatmap.
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        if kwargs is None:
            kwargs = {}
        colors = list(reversed(NONSYN_COLORS + ['k', 'lightgray']))
        sns.heatmap(df, cmap=colors, ax=ax, xticklabels=False, **kwargs)
        ax.set_xlabel('Samples')
        ax.set_ylabel('')

        # Modify the colorbar.
        cbar = ax.collections[0].colorbar
        r = cbar.vmax - cbar.vmin
        n = len(d)
        cbar.set_ticks([cbar.vmin + r / n * (0.5 + i) for i in range(n)])
        cbar.set_ticklabels(list(d.keys()))

        return ax

class AnnFrame:
    """Class for storing annotation data.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame containing annotation data.

    See Also
    --------
    AnnFrame.from_file
        Construct AnnFrame from an annotation file.
    """
    def __init__(self, df):
        self.df = df.reset_index(drop=True)

    @classmethod
    def from_file(cls, fn):
        """Construct AnnFrame from an annotation file.

        Parameters
        ----------
        fn : str
            Annotation file path (zipped or unzipped).

        Returns
        -------
        AnnFrame
            AnnFrame.

        See Also
        --------
        AnnFrame
            AnnFrame object creation using constructor.
        """
        return cls(pd.read_table(fn))
