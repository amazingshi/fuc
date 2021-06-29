"""
The pymaf submodule is designed for working with MAF files. It implements
``pymaf.MafFrame`` which stores MAF data as ``pandas.DataFrame`` to allow
fast computation and easy manipulation. The ``pymaf.MafFrame`` class also
contains many useful plotting methods such as ``MafFrame.plot_oncoplot`` and
``MafFrame.plot_summary``. The submodule strictly adheres to the
standard `MAF specification
<https://docs.gdc.cancer.gov/Data/File_Formats/MAF_Format/>`_.

A typical MAF file contains many fields ranging from gene symbol to
protein change. However, most of the analysis in pymaf uses the
following fields:

+-----+------------------------+----------------------+-------------------------------+
| No. | Name                   | Description          | Examples                      |
+=====+========================+======================+===============================+
| 1   | Hugo_Symbol            | HUGO gene symbol     | 'TP53', 'Unknown'             |
+-----+------------------------+----------------------+-------------------------------+
| 2   | Entrez_Gene_Id         | Entrez or Ensembl ID | 0, 8714                       |
+-----+------------------------+----------------------+-------------------------------+
| 3   | Center                 | Sequencing center    | '.', 'genome.wustl.edu'       |
+-----+------------------------+----------------------+-------------------------------+
| 4   | NCBI_Build             | Genome assembly      | '37', 'GRCh38'                |
+-----+------------------------+----------------------+-------------------------------+
| 5   | Chromosome             | Chromosome name      | 'chr1'                        |
+-----+------------------------+----------------------+-------------------------------+
| 6   | Start_Position         | Start coordinate     | 119031351                     |
+-----+------------------------+----------------------+-------------------------------+
| 7   | End_Position           | End coordinate       | 44079555                      |
+-----+------------------------+----------------------+-------------------------------+
| 8   | Strand                 | Genomic strand       | '+', '-'                      |
+-----+------------------------+----------------------+-------------------------------+
| 9   | Variant_Classification | Translational effect | 'Missense_Mutation', 'Silent' |
+-----+------------------------+----------------------+-------------------------------+
| 10  | Variant_Type           | Mutation type        | 'SNP', 'INS', 'DEL'           |
+-----+------------------------+----------------------+-------------------------------+
| 11  | Reference_Allele       | Reference allele     | 'T', '-', 'ACAA'              |
+-----+------------------------+----------------------+-------------------------------+
| 12  | Tumor_Seq_Allele1      | First tumor allele   | 'A', '-', 'TCA'               |
+-----+------------------------+----------------------+-------------------------------+
| 13  | Tumor_Seq_Allele2      | Second tumor allele  | 'A', '-', 'TCA'               |
+-----+------------------------+----------------------+-------------------------------+
| 14  | Tumor_Sample_Barcode   | Sample ID            | 'TCGA-AB-3002'                |
+-----+------------------------+----------------------+-------------------------------+
| 15  | Protein_Change         | Protein change       | 'p.L558Q'                     |
+-----+------------------------+----------------------+-------------------------------+

It is recommended to include additional custom fields such as variant
allele frequecy (VAF) and transcript name.

If sample annotation data are available for a given MAF file, use
the :class:`AnnFrame` class to import the data.
"""

import pandas as pd
import seaborn as sns
import numpy as np
import re
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.gridspec as gridspec
from . import pyvcf, common
import copy

# Below is the list of calculated variant consequences from Ensemble VEP:
# https://m.ensembl.org/info/genome/variation/prediction/predicted_data.html
# (accessed on 2021-05-31)
#
# Note that both frameshift_variant and protein_altering_variant require
# additional information to find their correct Variant_Classification.

MAF_HEADERS = [
    'Hugo_Symbol', 'Entrez_Gene_Id', 'Center', 'NCBI_Build', 'Chromosome',
    'Start_Position', 'End_Position', 'Strand', 'Variant_Classification',
    'Variant_Type', 'Reference_Allele', 'Tumor_Seq_Allele1',
    'Tumor_Seq_Allele2', 'Tumor_Sample_Barcode', 'Protein_Change'
]

VEP_CONSEQUENCES = {
    'transcript_ablation':                'Splice_Site',
    'splice_acceptor_variant':            'Splice_Site',
    'splice_donor_variant':               'Splice_Site',
    'stop_gained':                        'Nonsense_Mutation',
    'frameshift_variant':                 'AMBIGUOUS',
    'stop_lost':                          'Nonstop_Mutation',
    'start_lost':                         'Translation_Start_Site',
    'transcript_amplification':           'Intron',
    'inframe_insertion':                  'In_Frame_Ins',
    'inframe_deletion':                   'In_Frame_Del',
    'missense_variant':                   'Missense_Mutation',
    'protein_altering_variant':           'AMBIGUOUS',
    'splice_region_variant':              'Splice_Region',
    'incomplete_terminal_codon_variant':  'Silent',
    'start_retained_variant':             'Silent',
    'stop_retained_variant':              'Silent',
    'synonymous_variant':                 'Silent',
    'coding_sequence_variant':            'Missense_Mutation',
    'mature_miRNA_variant':               'RNA',
    '5_prime_UTR_variant':                "5'UTR",
    '3_prime_UTR_variant':                "3'UTR",
    'non_coding_transcript_exon_variant': 'RNA',
    'intron_variant':                     'Intron',
    'NMD_transcript_variant':             'Silent',
    'non_coding_transcript_variant':      'RNA',
    'upstream_gene_variant':              "5'Flank",
    'downstream_gene_variant':            "3'Flank",
    'TFBS_ablation':                      'Targeted_Region',
    'TFBS_amplification':                 'Targeted_Region',
    'TF_binding_site_variant':            'IGR',
    'regulatory_region_ablation':         'Targeted_Region',
    'regulatory_region_amplification':    'Targeted_Region',
    'feature_elongation':                 'Targeted_Region',
    'regulatory_region_variant':          'IGR',
    'feature_truncation':                 'Targeted_Region',
    'intergenic_variant':                 'IGR',
}

VARCLS_LIST = [
    "3'Flank",
    "3'UTR",
    "5'Flank",
    "5'UTR",
    'De_novo_Start_InFrame',
    'De_novo_Start_OutOfFrame',
    'Frame_Shift_Del',
    'Frame_Shift_Ins',
    'IGR',
    'In_Frame_Del',
    'In_Frame_Ins',
    'Intron',
    'Missense_Mutation',
    'Nonsense_Mutation',
    'Nonstop_Mutation',
    'RNA',
    'Silent',
    'Splice_Region',
    'Splice_Site',
    'Start_Codon_Ins',
    'Start_Codon_SNP',
    'Stop_Codon_Del',
    'Targeted_Region',
    'Translation_Start_Site',
    'lincRNA',
]

NONSYN_NAMES = [
    'Missense_Mutation', 'Frame_Shift_Del', 'Frame_Shift_Ins',
    'In_Frame_Del', 'In_Frame_Ins', 'Nonsense_Mutation',
    'Nonstop_Mutation', 'Splice_Site', 'Translation_Start_Site'
]

NONSYN_COLORS = [
    'tab:green', 'tab:blue', 'tab:purple', 'tab:olive', 'tab:red',
    'tab:cyan', 'tab:pink', 'tab:orange', 'tab:brown'
]

SNV_CLASSES = {
    'A>C': {'class': 'T>G', 'type': 'Tv'},
    'A>G': {'class': 'T>C', 'type': 'Ti'},
    'A>T': {'class': 'T>A', 'type': 'Tv'},
    'C>A': {'class': 'C>A', 'type': 'Tv'},
    'C>G': {'class': 'C>G', 'type': 'Tv'},
    'C>T': {'class': 'C>T', 'type': 'Ti'},
    'G>A': {'class': 'C>T', 'type': 'Ti'},
    'G>C': {'class': 'C>G', 'type': 'Tv'},
    'G>T': {'class': 'C>A', 'type': 'Tv'},
    'T>A': {'class': 'T>A', 'type': 'Tv'},
    'T>C': {'class': 'T>C', 'type': 'Ti'},
    'T>G': {'class': 'T>G', 'type': 'Tv'},
}

def legend_handles(name='regular'):
    """Return legend handles for one of the pre-defined legends.

    Parameters
    ----------
    name : {'regaulr', 'waterfall'}, default: 'regular'
        Type of legend to be drawn. See the examples below for details.

    Returns
    -------
    list
        Legend handles.

    Examples
    --------
    There are currently two types of legends:

    .. plot::
        :context: close-figs

        >>> import matplotlib.pyplot as plt
        >>> from fuc import pymaf
        >>> fig, ax = plt.subplots()
        >>> handles1 = pymaf.legend_handles(name='regular')
        >>> handles2 = pymaf.legend_handles(name='waterfall')
        >>> leg1 = ax.legend(handles=handles1, title="name='regular'", loc='center left')
        >>> leg2 = ax.legend(handles=handles2, title="name='waterfall'", loc='center right')
        >>> ax.add_artist(leg1)
        >>> ax.add_artist(leg2)
        >>> plt.tight_layout()

    A common way of adding a legend is as follows:

    .. plot::
        :context: close-figs

        >>> from fuc import common
        >>> common.load_dataset('tcga-laml')
        >>> mf = pymaf.MafFrame.from_file('~/fuc-data/tcga-laml/tcga_laml.maf.gz')
        >>> fig, [ax1, ax2] = plt.subplots(2, 1, figsize=(10, 6), gridspec_kw={'height_ratios': [10, 1]})
        >>> mf.plot_waterfall(ax=ax1, linewidths=0.5)
        >>> handles = pymaf.legend_handles(name='waterfall')
        >>> ax2.legend(handles=handles, ncol=4, loc='upper center', title='Variant_Classification')
        >>> ax2.axis('off')
        >>> plt.tight_layout()

    Alternatively, you can insert a legend directly to an existing plot:

    .. plot::
        :context: close-figs

        >>> ax = mf.plot_genes()
        >>> handles = pymaf.legend_handles(name='regular')
        >>> ax.legend(handles=handles, title='Variant_Classification')
        >>> plt.tight_layout()
    """
    handles = []
    labels = copy.deepcopy(NONSYN_NAMES)
    colors = copy.deepcopy(NONSYN_COLORS)
    if name == 'regular':
        pass
    elif name == 'waterfall':
        labels += ['Multi_Hit']
        colors += ['k']
    else:
        raise ValueError(f'Found incorrect name: {name}')
    for i, label in enumerate(labels):
        handles.append(mpatches.Patch(color=colors[i], label=label))
    return handles

class AnnFrame:
    """
    Class for storing sample annotation data.

    This class stores sample annotation data as :class:`pandas.DataFrame`
    with sample names as index.

    Note that an AnnFrame can have a different set of samples than its
    accompanying MafFrame.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame containing sample annotation data. The index must be
        sample names.

    See Also
    --------
    AnnFrame.from_dict
        Construct AnnFrame from dict of array-like or dicts.
    AnnFrame.from_file
        Construct AnnFrame from a delimited text file.

    Examples
    --------

    >>> import pandas as pd
    >>> from fuc import pymaf
    >>> data = {
    ...     'Tumor_Sample_Barcode': ['Steven_N', 'Steven_T', 'Sara_N', 'Sara_T'],
    ...     'Subject': ['Steven', 'Steven', 'Sara', 'Sara'],
    ...     'Type': ['Normal', 'Tumor', 'Normal', 'Tumor'],
    ...     'Age': [30, 30, 57, 57]
    ... }
    >>> df = pd.DataFrame(data)
    >>> df = df.set_index('Tumor_Sample_Barcode')
    >>> af = pymaf.AnnFrame(df)
    >>> af.df
                         Subject    Type  Age
    Tumor_Sample_Barcode
    Steven_N              Steven  Normal   30
    Steven_T              Steven   Tumor   30
    Sara_N                  Sara  Normal   57
    Sara_T                  Sara   Tumor   57
    """

    def _check_df(self, df):
        if type(df.index) == pd.RangeIndex:
            m = "Index must be sample names, not 'pandas.RangeIndex'."
            raise ValueError(m)
        return df

    def __init__(self, df):
        self._df = self._check_df(df)

    @property
    def df(self):
        """pandas.DataFrame : DataFrame containing sample annotation data."""
        return self._df

    @df.setter
    def df(self, value):
        self._df = self._check_df(value)

    @property
    def samples(self):
        """list : List of the sample names."""
        return list(self.df.index.to_list())

    @property
    def shape(self):
        """tuple : Dimensionality of AnnFrame (samples, annotations)."""
        return self.df.shape

    def filter_mf(self, mf):
        """
        Filter the AnnFrame for the samples in the MafFrame.

        Parameters
        ----------
        mf : MafFrame
            MafFrame containing target samples.

        Returns
        -------
        AnnFrame
            Filtered AnnFrame object.
        """
        df = self.df.loc[mf.samples]
        return self.__class__(df)

    @classmethod
    def from_dict(cls, data, sample_col='Tumor_Sample_Barcode'):
        """Construct AnnFrame from dict of array-like or dicts.

        The dictionary must have at least one column that represents sample
        names which are used as index for pandas.DataFrame.

        Parameters
        ----------
        data : dict
            Of the form {field : array-like} or {field : dict}.
        sample_col : str, default: 'Tumor_Sample_Barcode'
            Column containing sample names.

        Returns
        -------
        AnnFrame
            AnnFrame object.

        See Also
        --------
        AnnFrame
            AnnFrame object creation using constructor.
        AnnFrame.from_file
            Construct AnnFrame from a delimited text file.

        Examples
        --------

        >>> from fuc import pymaf
        >>> data = {
        ...     'Tumor_Sample_Barcode': ['Steven_Normal', 'Steven_Tumor', 'Sara_Normal', 'Sara_Tumor'],
        ...     'Subject': ['Steven', 'Steven', 'Sara', 'Sara'],
        ...     'Type': ['Normal', 'Tumor', 'Normal', 'Tumor'],
        ...     'Age': [30, 30, 57, 57]
        ... }
        >>> af = pymaf.AnnFrame.from_dict(data)
        >>> af.df
                             Subject    Type  Age
        Tumor_Sample_Barcode
        Steven_Normal         Steven  Normal   30
        Steven_Tumor          Steven   Tumor   30
        Sara_Normal             Sara  Normal   57
        Sara_Tumor              Sara   Tumor   57
        """
        df = pd.DataFrame(data)
        df = df.set_index(sample_col)
        return cls(df)

    @classmethod
    def from_file(cls, fn, sample_col='Tumor_Sample_Barcode', sep='\t'):
        """
        Construct an AnnFrame from a delimited text file.

        The text file must have at least one column that represents
        sample names which are used as index for pandas.DataFrame.

        Parameters
        ----------
        fn : str
            Text file path (zipped or unzipped).
        sample_col : str, default: 'Tumor_Sample_Barcode'
            Column containing sample names.
        sep : str, default: '\\\\t'
            Delimiter to use.

        Returns
        -------
        AnnFrame
            AnnFrame.

        See Also
        --------
        AnnFrame
            AnnFrame object creation using constructor.
        AnnFrame.from_dict
            Construct AnnFrame from dict of array-like or dicts.

        Examples
        --------

        >>> from fuc import pymaf
        >>> af1 = pymaf.AnnFrame.from_file('sample-annot-1.tsv')
        >>> af2 = pymaf.AnnFrame.from_file('sample-annot-2.csv', sample_col='SampleID', sep=',')
        """
        df = pd.read_table(fn, sep=sep)
        df = df.set_index(sample_col)
        return cls(df)

    def legend_handles(
        self, col, samples=None, numeric=False, segments=5, decimals=0,
        cmap='Pastel1'
    ):
        """Return legend handles for the given column.

        In the case of a numeric column, use ``numeric=True`` which will
        divide the values into equal-sized intervals, with the number of
        intervals determined by the `segments` option.

        Parameters
        ----------
        col : str
            Column name.
        samples : list, optional
            If provided, these samples will be used to create legend handles.
        numeric : bool, default: False
            If True, the column will be treated as numeric.
        segments : int, default: 5
            If ``numeric`` is True, the numbers will be divided
            into this number of equal-sized segments.
        decimals : int, default: 0
            If ``numeric`` is True, the numbers will be rounded up to this
            number of decimals.
        cmap : str, default: 'Pastel1'
            Color map.

        Returns
        -------
        list
            Legend handles.

        See Also
        --------
        AnnFrame.plot_annot
            Create a 1D categorical heatmap for the given column.

        Examples
        --------

        .. plot::

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> f = '~/fuc-data/tcga-laml/tcga_laml_annot.tsv'
            >>> af = pymaf.AnnFrame.from_file(f)
            >>> fig, ax = plt.subplots()
            >>> handles1 = af.legend_handles('FAB_classification',
            ...                              cmap='Dark2')
            >>> handles2 = af.legend_handles('days_to_last_followup',
            ...                              numeric=True,
            ...                              cmap='viridis')
            >>> handles3 = af.legend_handles('Overall_Survival_Status')
            >>> leg1 = ax.legend(handles=handles1,
            ...                  title='FAB_classification',
            ...                  loc='center left')
            >>> leg2 = ax.legend(handles=handles2,
            ...                  title='days_to_last_followup',
            ...                  loc='center')
            >>> leg3 = ax.legend(handles=handles3,
            ...                  title='Overall_Survival_Status',
            ...                  loc='center right')
            >>> ax.add_artist(leg1)
            >>> ax.add_artist(leg2)
            >>> ax.add_artist(leg3)
            >>> plt.tight_layout()
        """
        s, l = self._get_col(col, numeric=numeric, segments=segments,
            samples=samples)
        colors = plt.cm.get_cmap(cmap)(np.linspace(0, 1, len(l)))
        handles = []
        for i, label in enumerate(l):
            handles.append(mpatches.Patch(color=colors[i], label=label))
        return handles

    def _get_col(
        self, col, numeric=False, segments=5, samples=None, decimals=0
    ):
        s = self.df[col]
        s = s.replace([np.inf, -np.inf], np.nan)
        if numeric:
            boundaries = list(np.linspace(s.min(), s.max(),
                segments+1, endpoint=True))
            intervals = list(zip(boundaries[:-1], boundaries[1:]))
            def f(x):
                if pd.isna(x):
                    return x
                for i, interval in enumerate(intervals):
                    a, b = interval
                    if a <= x <= b:
                        return f'G{i} ({b:.{decimals}f})'
            s = s.apply(f)
        if samples is not None:
            s = s[samples]
        l = sorted([x for x in s.unique() if x == x])
        return s, l

    def plot_annot(
        self, col, samples=None, numeric=False, segments=5, decimals=0,
        cmap='Pastel1', ax=None, figsize=None, **kwargs
    ):
        """
        Create a 1D categorical heatmap of the column.

        In the case of a numeric column, set ``numeric`` as True which will
        divide the values into equal-sized intervals, with the number of
        intervals determined by ``segments``.

        See the :ref:`tutorials:Create customized oncoplots` tutorial to
        learn how to create customized oncoplots.

        Parameters
        ----------
        col : str
            Column name.
        samples : list, optional
            If provided, these samples will be used to create legend handles.
        numeric : bool, default: False
            If True, the column will be treated as numeric.
        segments : int, default: 5
            If ``numeric`` is True, the numbers will be divided
            into this number of equal-sized segments.
        decimals : int, default: 0
            If ``numeric`` is True, the numbers will be rounded up to this
            number of decimals.
        cmap : str, default: 'Pastel1'
            Color map.

        Returns
        -------
        list
            Legend handles.

        See Also
        --------
        AnnFrame.legend_handles
            Return legend handles for the given column.

        Examples
        --------

        .. plot::

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> f = '~/fuc-data/tcga-laml/tcga_laml_annot.tsv'
            >>> af = pymaf.AnnFrame.from_file(f)
            >>> fig, [ax1, ax2, ax3] = plt.subplots(3, 1, figsize=(10, 5))
            >>> af.plot_annot('FAB_classification', ax=ax1, linewidths=1, cmap='Dark2')
            >>> af.plot_annot('days_to_last_followup', ax=ax2, linewidths=1, cmap='viridis')
            >>> af.plot_annot('Overall_Survival_Status', ax=ax3, linewidths=1)
            >>> ax1.set_xlabel('')
            >>> ax2.set_xlabel('')
            >>> ax1.set_ylabel('')
            >>> ax2.set_ylabel('')
            >>> ax3.set_ylabel('')
            >>> plt.tight_layout()
            >>> plt.subplots_adjust(wspace=0.01, hspace=0.01)
        """
        s, l = self._get_col(col, numeric=numeric, segments=segments,
            samples=samples)
        d = {k: v for v, k in enumerate(l)}
        df = s.to_frame().applymap(lambda x: x if pd.isna(x) else d[x])
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        sns.heatmap(df.T, ax=ax, cmap=cmap, cbar=False, **kwargs)
        ax.set_xlabel('Samples')
        ax.set_ylabel(col)
        ax.set_xticks([])
        ax.set_yticks([])
        return ax

    def sorted_samples(self, by, mf=None, keep_empty=False, nonsyn=False):
        """
        Return a sorted list of sample names.

        Parameters
        ----------
        df : str or list
            Column or list of columns to sort by.
        """
        df = self.df.copy()

        if nonsyn:
            samples = mf.matrix_waterfall(keep_empty=keep_empty).columns
            df = df.loc[samples]

        df = df.sort_values(by=by)

        return df.index.to_list()

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
        """
        Construct a MafFrame from a MAF file.

        Parameters
        ----------
        fn : str
            MAF file (zipped or unzipped).

        Returns
        -------
        MafFrame
            MafFrame object.

        See Also
        --------
        MafFrame
            MafFrame object creation using constructor.

        Examples
        --------

        >>> from fuc import common, pymaf
        >>> common.load_dataset('tcga-laml')
        >>> fn = '~/fuc-data/tcga-laml/tcga_laml.maf.gz'
        >>> mf = pymaf.MafFrame.from_file(fn)
        """
        # Read the MAF file.
        df = pd.read_table(fn)

        # Check the required columns. Letter case matters.
        case_dict = {}
        for c1 in MAF_HEADERS:
            found = False
            for c2 in df.columns:
                if c1 == c2:
                    found = True
                    break
                if c1.lower() == c2.lower():
                    found = True
                    case_dict[c2] = c1
                    break
            if not found:
                raise ValueError(f"Required column '{c1}' is not found.")

        # If necessary, match the letter case.
        if case_dict:
            df = df.rename(columns=case_dict)

        # Set the data types.
        df.Chromosome = df.Chromosome.astype(str)

        return cls(df)

    @classmethod
    def from_vcf(cls, vcf, keys=None, names=None):
        """Construct a MafFrame from a VCF file or VcfFrame.

        The input VCF should already contain functional annotation data
        from a tool such as Ensemble VEP, SnpEff, and ANNOVAR. The
        recommended method is Ensemble VEP with "RefSeq transcripts" as the
        transcript database and the filtering option "Show one selected
        consequence per variant".

        Parameters
        ----------
        vcf : str or VcfFrame
            VCF file or VcfFrame.
        keys : str or list
            Genotype key or list of genotype keys.
        names : str or list
            Column name or list of column names to use in the MafFrame.

        Examples
        --------

        >>> from fuc import pymaf
        >>> mf = pymaf.MafFrame.from_vcf('annotated.vcf')
        """
        # Parse the input VCF.
        if isinstance(vcf, str):
            vf = pyvcf.VcfFrame.from_file(vcf)
        else:
            vf = vcf

        # Get the NCBI_Build data.
        for line in vf.meta:
            if line.startswith('##VEP'):
                ncbi_build = re.search(r'assembly="(.*?)"', line).group(1)

        # Define the conversion algorithm.
        def one_row(r):
            fields = r.INFO.replace('CSQ=', '').split(',')[0].split('|')

            # Get the sequence data.
            inframe = abs(len(r.REF) - len(r.ALT)) / 3 == 0
            if len(r.REF) == len(r.ALT) == 1:
                variant_type = 'SNP'
                start_position = r.POS
                end_position = r.POS
                reference_allele = r.REF
                tumor_seq_allele1 = r.ALT
                tumor_seq_allele2 = r.ALT
            elif len(r.REF) > len(r.ALT):
                variant_type = 'DEL'
                start_position = r.POS + 1
                end_position = r.POS + len(r.REF) - len(r.ALT)
                reference_allele = r.REF[1:]
                tumor_seq_allele1 = '-'
                tumor_seq_allele2 = '-'
            else:
                variant_type = 'INS'
                start_position = r.POS
                end_position = r.POS + 1
                reference_allele = '-'
                tumor_seq_allele1 = r.ALT[1:]
                tumor_seq_allele2 = r.ALT[1:]

            # Get the Strand data.
            strand = '+' if fields[19] == '1' else '-'

            # Get the Variant_Classification data.
            consequence = fields[1].split('&')[0]
            if consequence == 'frameshift_variant':
                if variant_type == 'DEL':
                    variant_classification = 'Frame_Shift_Del'
                else:
                    variant_classification = 'Frame_Shift_Ins'
            elif consequence == 'protein_altering_variant':
                if inframe:
                    if variant_type == 'DEL':
                        variant_classification = 'In_Frame_Del'
                    else:
                        variant_classification = 'In_Frame_Ins'
                else:
                    if variant_type == 'DEL':
                        variant_classification = 'Frame_Shift_Del'
                    else:
                        variant_classification = 'Frame_Shift_Ins'
            elif consequence in VEP_CONSEQUENCES:
                variant_classification = VEP_CONSEQUENCES[consequence]
            else:
                m = f'Found unknown Ensemble VEP consequence: {consequence}'
                raise ValueError(m)

            # Get the Tumor_Sample_Barcode data.
            s = r[9:].apply(pyvcf.gt_hasvar)
            tumor_sample_barcode = ','.join(s[s].index.to_list())

            # Get the Protein_Change data.
            pos = fields[14]
            aa = fields[15].split('/')
            if len(aa) > 1:
                protein_change = f'p.{aa[0]}{pos}{aa[1]}'
            else:
                protein_change = '.'

            d = dict(
                Hugo_Symbol = fields[3],
                Entrez_Gene_Id = fields[4],
                Center = '.',
                NCBI_Build = ncbi_build,
                Chromosome = r.CHROM,
                Start_Position = start_position,
                End_Position = end_position,
                Strand = strand,
                Variant_Classification = variant_classification,
                Variant_Type = variant_type,
                Reference_Allele = reference_allele,
                Tumor_Seq_Allele1 = tumor_seq_allele1,
                Tumor_Seq_Allele2 = tumor_seq_allele2,
                Tumor_Sample_Barcode = tumor_sample_barcode,
                Protein_Change = protein_change,
                CHROM = r.CHROM,
                POS = r.POS,
                REF = r.REF,
                ALT = r.ALT,
            )

            return pd.Series(d)

        # Apply the conversion algorithm.
        df = vf.df.apply(one_row, axis=1)

        # Expand the Tumor_Sample_Barcode column to multiple rows.
        s = df['Tumor_Sample_Barcode'].str.split(',').apply(
            pd.Series, 1).stack()
        s.index = s.index.droplevel(-1)
        s.name = 'Tumor_Sample_Barcode'
        del df['Tumor_Sample_Barcode']
        df = df.join(s)

        # Append the genotype keys.
        if keys is None:
            keys = []
        if names is None:
            names = []
        if isinstance(keys, str):
            keys = [keys]
        if isinstance(names, str):
            names = [names]
        for i, key in enumerate(keys):
            temp_df = vf.extract(key)
            temp_df = pd.concat([vf.df.iloc[:, :9], temp_df], axis=1)
            temp_df = temp_df.drop(
                columns=['ID', 'QUAL', 'FILTER', 'INFO', 'FORMAT'])
            temp_df = pd.melt(
                temp_df,
                id_vars=['CHROM', 'POS', 'REF', 'ALT'],
                var_name='Tumor_Sample_Barcode',
            )
            temp_df = temp_df[temp_df.value != '.']
            df = df.merge(temp_df,
                on=['CHROM', 'POS', 'REF', 'ALT', 'Tumor_Sample_Barcode'])
            df = df.rename(columns={'value': names[i]})

        df = df.drop(columns=['CHROM', 'POS', 'REF', 'ALT'])

        return cls(df)

    def matrix_genes(self, count=10, mode='variants'):
        """
        Compute a matrix of variant counts with a shape of (genes, variant
        classifications).

        Parameters
        ----------
        count : int, default: 10
            Number of top mutated genes to display.

        Returns
        -------
        pandas.DataFrame
            Dataframe containing TMB data.
        """
        if mode == 'variants':
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
            df = df.rename_axis(None, axis=1)
        elif mode == 'samples':
            df = self.matrix_waterfall(count)
            df = df.apply(lambda r: r.value_counts(), axis=1)
            for varcls in NONSYN_NAMES + ['Multi_Hit']:
                if varcls not in df.columns:
                    df[varcls] = np.nan
            df = df[NONSYN_NAMES + ['Multi_Hit']]
            df = df.fillna(0)
        else:
            raise ValueError(f'Found incorrect mode: {mode}')
        return df

    def matrix_tmb(self):
        """
        Compute a matrix of variant counts with a shape of (samples, variant
        classifications).

        Returns
        -------
        pandas.DataFrame
            Dataframe containing TMB data.
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
        return df

    def matrix_waterfall(self, count=10, keep_empty=False):
        """
        Compute a matrix of variant classifications with a shape of
        (genes, samples).

        If there are multiple variant classifications available for a given
        cell, they will be replaced as 'Multi_Hit'.

        Parameters
        ----------
        count : int, default: 10
            Number of top mutated genes to include.
        keep_empty : bool, default: False
            If True, keep samples with all ``NaN``'s.

        Returns
        -------
        pandas.DataFrame
            Dataframe containing waterfall data.
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

        # Drop samples with all NaN's.
        if not keep_empty:
            df = df.dropna(axis=1, how='all')

        # Sort the columns (samples).
        c = df.applymap(lambda x: 0 if pd.isnull(x) else 1).sort_values(
            df.index.to_list(), axis=1, ascending=False).columns
        df = df[c]
        df = df.fillna('None')
        df = df.rename_axis(None, axis=1)

        return df

    def plot_genes(
        self, count=10, mode='variants', ax=None, figsize=None, **kwargs
    ):
        """
        Create a bar plot showing variant distirbution for top mutated genes.

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
            :context: close-figs

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> f = '~/fuc-data/tcga-laml/tcga_laml.maf.gz'
            >>> mf = pymaf.MafFrame.from_file(f)
            >>> mf.plot_genes(mode='variants')
            >>> plt.tight_layout()

        .. plot::
            :context: close-figs

            >>> mf.plot_genes(mode='samples')
            >>> plt.tight_layout()
        """
        if mode == 'variants':
            colors = NONSYN_COLORS
        elif mode == 'samples':
            colors = NONSYN_COLORS + ['k']
        else:
            raise ValueError(f'Found incorrect mode: {mode}')
        df = self.matrix_genes(count, mode=mode)
        df = df.iloc[::-1]
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        df.plot.barh(stacked=True, ax=ax, color=colors,
            legend=False, **kwargs)
        ax.set_xlabel('Count')
        ax.set_ylabel('')
        return ax

    def plot_oncoplot(
        self, count=10, keep_empty=False, figsize=(15, 10), label_fontsize=15,
        ticklabels_fontsize=15, legend_fontsize=15
    ):
        """
        Create a standard oncoplot.

        See the :ref:`tutorials:Create customized oncoplots` tutorial to
        learn how to create customized oncoplots.

        Parameters
        ----------
        count : int, default: 10
            Number of top mutated genes to display.
        keep_empty : bool, default: False
            If True, display samples that do not have any mutations.
        figsize : tuple, default: (15, 10)
            Width, height in inches. Format: (float, float).
        label_fontsize : float, default: 15
            Font size of labels.
        ticklabels_fontsize : float, default: 15
            Font size of tick labels.
        legend_fontsize : float, default: 15
            Font size of legend texts.

        Examples
        --------

        .. plot::

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> maf_file = '~/fuc-data/tcga-laml/tcga_laml.maf.gz'
            >>> mf = pymaf.MafFrame.from_file(maf_file)
            >>> mf.plot_oncoplot()
        """
        g = {'height_ratios': [1, 10, 1], 'width_ratios': [10, 1]}
        fig, axes = plt.subplots(3, 2, figsize=figsize, gridspec_kw=g)
        [[ax1, ax2], [ax3, ax4], [ax5, ax6]] = axes

        # Create the TMB plot.
        samples = list(self.matrix_waterfall(count=count,
            keep_empty=keep_empty).columns)
        self.plot_tmb(ax=ax1, samples=samples, width=0.95)
        ax1.set_xlabel('')
        ax1.spines['right'].set_visible(False)
        ax1.spines['top'].set_visible(False)
        ax1.spines['bottom'].set_visible(False)
        ax1.set_xlim(-0.5, len(samples)-0.5)
        ax1.set_ylabel('TMB', fontsize=label_fontsize)
        ax1.set_yticks([0, self.matrix_tmb().sum(axis=1).max()])
        ax1.tick_params(axis='y', which='major',
                        labelsize=ticklabels_fontsize)

        # Remove the top right plot.
        ax2.remove()

        # Create the waterfall plot.
        self.plot_waterfall(count=count, ax=ax3, linewidths=1, keep_empty=keep_empty)
        ax3.set_xlabel('')
        ax3.tick_params(axis='y', which='major', labelrotation=0,
                        labelsize=ticklabels_fontsize)

        # Create the genes plot.
        self.plot_genes(count=count, ax=ax4, mode='samples', width=0.95)
        ax4.spines['right'].set_visible(False)
        ax4.spines['left'].set_visible(False)
        ax4.spines['top'].set_visible(False)
        ax4.set_yticks([])
        ax4.set_xlabel('Samples', fontsize=label_fontsize)
        ax4.set_xticks([0, self.matrix_genes(
            10, mode='samples').sum(axis=1).max()])
        ax4.set_ylim(-0.5, count-0.5)
        ax4.tick_params(axis='x', which='major',
                        labelsize=ticklabels_fontsize)

        # Create the legend.
        ax5.legend(handles=legend_handles('waterfall'),
                   title='Variant_Classification',
                   loc='upper center',
                   ncol=4,
                   fontsize=legend_fontsize,
                   title_fontsize=legend_fontsize)
        ax5.axis('off')

        # Remove the bottom right plot.
        ax6.remove()

        plt.tight_layout()
        plt.subplots_adjust(wspace=0.01, hspace=0.01)

    def plot_snvcls(
        self, mode='count', cmap='Pastel1', flip=False, ax=None,
        figsize=None, **kwargs
    ):
        """
        Create various kinds of plot showing the distrubtion of SNV classes.

        Parameters
        ----------
        mode : {'count', 'proportion', 'samples'}, default: 'count'
            Determines the plotting mode.

            - ``count``: Bar plot showing the total counts of SNV classes
              for all samples. It uses :meth:`seaborn.barplot` as the
              plotting method.
            - ``proportion``: Box plot showing the proportions of SNV classes
              for all samples. It uses :meth:`seaborn.boxplot` as the
              plotting method.
            - ``samples``: Stacked bar plot showing the proportions of SNV classes
              for each sample. It uses :meth:`pandas.DataFrame.plot.bar/barh`
              as the plotting method.

        cmap : str, default: 'Pastel1'
            Name of the colormap according to :meth:`matplotlib.cm.get_cmap`.
        flip : bool, default: False
            If True, flip the x and y axes.
        ax : matplotlib.axes.Axes, optional
            Pre-existing axes for the plot. Otherwise, crete a new one.
        figsize : tuple, optional
            Width, height in inches. Format: (float, float).
        kwargs
            Other keyword arguments will be passed down to the respective
            plotting method.

        Returns
        -------
        matplotlib.axes.Axes
            The matplotlib axes containing the plot.

        Examples
        --------

        .. plot::
            :context: close-figs

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> f = '~/fuc-data/tcga-laml/tcga_laml.maf.gz'
            >>> mf = pymaf.MafFrame.from_file(f)
            >>> mf.plot_snvcls()
            >>> plt.tight_layout()

        .. plot::
            :context: close-figs

            >>> mf.plot_snvcls(mode='proportion')
            >>> plt.tight_layout()

        .. plot::
            :context: close-figs

            >>> mf.plot_snvcls(mode='samples')
            >>> plt.tight_layout()
        """
        modes = {
            'count': self._plot_snvcls_count,
            'proportion': self._plot_snvcls_proportion,
            'samples': self._plot_snvcls_samples,
        }
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        df = self.df[self.df.Variant_Type == 'SNP']
        def one_row(r):
            change = r.Reference_Allele + '>' + r.Tumor_Seq_Allele2
            return SNV_CLASSES[change]['class']
        s = df.apply(one_row, axis=1)
        s.name = 'SNV_Class'
        df = pd.concat([df, s], axis=1)
        ax = modes[mode](df, flip, ax, cmap, **kwargs)
        return ax

    def _plot_snvcls_count(self, df, flip, ax, cmap, **kwargs):
        s = df.SNV_Class.value_counts()
        i = sorted(set([v['class'] for k, v in SNV_CLASSES.items()]))
        s = s.reindex(index=i)
        df = s.to_frame().reset_index()
        df.columns = ['SNV_Class', 'Count']
        kwargs = {'ax': ax,
                  'data': df,
                  'palette': cmap,
                  **kwargs}
        if flip:
            sns.barplot(x='SNV_Class', y='Count', **kwargs)
            ax.set_xlabel('')
        else:
            sns.barplot(x='Count', y='SNV_Class', **kwargs)
            ax.set_ylabel('')
        return ax

    def _plot_snvcls_proportion(self, df, flip, ax, cmap, **kwargs):
        s = df.groupby('Tumor_Sample_Barcode')['SNV_Class'].value_counts()
        s.name = 'Count'
        df = s.to_frame().reset_index()
        df = df.pivot(index='Tumor_Sample_Barcode', columns='SNV_Class')
        df = df.fillna(0)
        df = df.apply(lambda r: r/r.sum(), axis=1)
        df.columns = df.columns.get_level_values(1)
        df.columns.name = ''
        df = pd.melt(df, var_name='SNV_Class', value_name='Proportion')
        kwargs = {'ax': ax,
                  'data': df,
                  'palette': cmap,
                  **kwargs}
        if flip:
            sns.boxplot(x='Proportion', y='SNV_Class', **kwargs)
            ax.set_ylabel('')
        else:
            sns.boxplot(x='SNV_Class', y='Proportion', **kwargs)
            ax.set_xlabel('')
        return ax

    def _plot_snvcls_samples(self, df, flip, ax, cmap, **kwargs):
        s = df.groupby('Tumor_Sample_Barcode')['SNV_Class'].value_counts()
        s.name = 'Count'
        df = s.to_frame().reset_index()
        df = df.pivot(index='Tumor_Sample_Barcode', columns='SNV_Class')
        df = df.fillna(0)
        df = df.apply(lambda r: r/r.sum(), axis=1)
        df.columns = df.columns.get_level_values(1)
        df.columns.name = ''
        kwargs = {'ax': ax,
                  'stacked': True,
                  'legend': False,
                  'width': 1,
                  'color': plt.cm.get_cmap(cmap).colors,
                  **kwargs}
        if flip:
            df.plot.barh(**kwargs)
            ax.set_yticks([])
            ax.set_xlabel('Proportion')
            ax.set_ylabel('Samples')
        else:
            df.plot.bar(**kwargs)
            ax.set_xticks([])
            ax.set_xlabel('Samples')
            ax.set_ylabel('Proportion')
        return ax

    def plot_titv(
        self, af=None, hue=None, hue_order=None, flip=False, ax=None,
        figsize=None, **kwargs
    ):
        """
        Create a box plot showing the proportions of Ti and Tv.

        A grouped box plot can be created with ``hue`` (requires an
        AnnFrame).

        Parameters
        ----------
        af : AnnFrame, optional
            AnnFrame containing sample annotation data.
        hue : str, optional
            Column in the AnnFrame containing information about sample groups.
        hue_order : list, optional
            Order to plot the group levels in.
        flip : bool, default: False
            If True, flip the x and y axes.
        ax : matplotlib.axes.Axes, optional
            Pre-existing axes for the plot. Otherwise, crete a new one.
        figsize : tuple, optional
            Width, height in inches. Format: (float, float).
        kwargs
            Other keyword arguments will be passed down to
            :meth:`seaborn.boxplot`.

        Returns
        -------
        matplotlib.axes.Axes
            The matplotlib axes containing the plot.

        Examples
        --------

        Below is a simple example:

        .. plot::
            :context: close-figs

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> maf_file = '~/fuc-data/tcga-laml/tcga_laml.maf.gz'
            >>> mf = pymaf.MafFrame.from_file(maf_file)
            >>> mf.plot_titv()
            >>> plt.tight_layout()

        We can create a grouped bar plot based on FAB classification:

        .. plot::
            :context: close-figs

            >>> annot_file = '~/fuc-data/tcga-laml/tcga_laml_annot.tsv'
            >>> af = pymaf.AnnFrame.from_file(annot_file)
            >>> mf.plot_titv(af=af,
            ...              hue='FAB_classification',
            ...              hue_order=['M0', 'M1', 'M2'])
            >>> plt.tight_layout()
        """
        df = self.df[self.df.Variant_Type == 'SNP']
        def one_row(r):
            change = r.Reference_Allele + '>' + r.Tumor_Seq_Allele2
            return SNV_CLASSES[change]['type']
        s = df.apply(one_row, axis=1)
        s.name = 'SNV_Type'
        df = pd.concat([df, s], axis=1)
        s = df.groupby('Tumor_Sample_Barcode')['SNV_Type'].value_counts()
        s.name = 'Count'
        df = s.to_frame().reset_index()
        df = df.pivot(index='Tumor_Sample_Barcode', columns='SNV_Type')

        df = df.fillna(0)
        df = df.apply(lambda r: r/r.sum(), axis=1)
        df.columns = df.columns.get_level_values(1)
        df.columns.name = ''

        if hue is not None:
            df = pd.merge(df, af.df[hue], left_index=True, right_index=True)
            df = df.reset_index(drop=True)
            df = df.set_index(hue)
            df = pd.melt(df, var_name='SNV_Type', value_name='Proportion',
                ignore_index=False)
            df = df.reset_index()
        else:
            df = pd.melt(df, var_name='SNV_Type', value_name='Proportion')

        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)

        if flip:
            x, y = 'Proportion', 'SNV_Type'
            xlabel, ylabel = 'Proportion', ''
        else:
            x, y = 'SNV_Type', 'Proportion'
            xlabel, ylabel = '', 'Proportion'

        sns.boxplot(x=x, y=y, data=df, hue=hue, hue_order=hue_order, ax=ax,
            **kwargs)

        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)

        return ax

    def plot_summary(
        self, figsize=(15, 10), title_fontsize=16, ticklabels_fontsize=12,
        legend_fontsize=12

    ):
        """Create a summary figure for MafFrame.

        Parameters
        ----------
        figsize : tuple, default: (15, 10)
            Width, height in inches. Format: (float, float).
        title_fontsize : float, default: 16
            Font size of subplot titles.
        ticklabels_fontsize : float, default: 12
            Font size of tick labels.
        legend_fontsize : float, default: 12
            Font size of legend texts.

        Examples
        --------

        .. plot::

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> f = '~/fuc-data/tcga-laml/tcga_laml.maf.gz'
            >>> mf = pymaf.MafFrame.from_file(f)
            >>> mf.plot_summary()
        """
        g = {'height_ratios': [10, 10, 1]}
        fig, axes = plt.subplots(3, 3, figsize=figsize, gridspec_kw=g)
        [[ax1, ax2, ax3], [ax4, ax5, ax6], [ax7, ax8, ax9]] = axes
        gs = axes[2, 0].get_gridspec()
        for ax in axes[2, :]:
            ax.remove()
        axbig = fig.add_subplot(gs[2, :])

        # Create the 'Variant classification (variants)' figure.
        self.plot_varcls(ax=ax1)
        ax1.set_yticks([])
        ax1.set_title('Variant classification (variants)',
                      fontsize=title_fontsize)
        ax1.set_xlabel('')
        ax1.tick_params(axis='x', which='major',
                        labelsize=ticklabels_fontsize)

        # Create the 'Variant type' figure.
        self.plot_vartype(ax=ax2)
        ax2.set_title('Variant type', fontsize=title_fontsize)
        ax2.set_xlabel('')
        ax2.tick_params(axis='both', which='major',
                        labelsize=ticklabels_fontsize)

        # Create the 'SNV class' figure.
        self.plot_snvcls(ax=ax3)
        ax3.set_title('SNV class', fontsize=title_fontsize)
        ax3.set_xlabel('')
        ax3.tick_params(axis='both', which='major',
                        labelsize=ticklabels_fontsize)

        # Create the 'Variants per sample' figure.
        median = self.matrix_tmb().sum(axis=1).median()
        self.plot_tmb(ax=ax4)
        ax4.set_title(f'Variants per sample (median={median:.1f})',
                      fontsize=title_fontsize)
        ax4.set_xlabel('')
        ax4.set_ylabel('')
        ax4.tick_params(axis='y', which='major',
                        labelsize=ticklabels_fontsize)

        ax4.axhline(y=median, color='red', linestyle='dashed')

        # Create the 'Variant classification (samples)' figure.
        self.plot_varsum(ax=ax5)
        ax5.set_title('Variant classification (samples)',
                      fontsize=title_fontsize)
        ax5.set_yticks([])
        ax5.set_xlabel('')
        ax5.tick_params(axis='x', which='major',
                        labelsize=ticklabels_fontsize)

        # Create the 'Top 10 mutated genes' figure.
        self.plot_genes(ax=ax6)
        ax6.set_title('Top 10 mutated genes', fontsize=title_fontsize)
        ax6.set_xlabel('')
        ax6.tick_params(axis='both', which='major',
                        labelsize=ticklabels_fontsize)

        # Add the legend.
        axbig.legend(handles=legend_handles('regular'),
                     title='Variant_Classification',
                     loc='upper center',
                     ncol=3,
                     fontsize=legend_fontsize,
                     title_fontsize=legend_fontsize)
        axbig.axis('off')

        plt.tight_layout()

    def plot_tmb(self, samples=None, width=0.8, ax=None, figsize=None, **kwargs):
        """
        Create a bar plot showing the :ref:`TMB <glossary:Tumor mutational
        burden (TMB)>` distributions of samples.

        Parameters
        ----------
        samples : list, optional
            Samples to be drawn (in the exact order).
        width : float, default: 0.8
            The width of the bars.
        ax : matplotlib.axes.Axes, optional
            Pre-existing axes for the plot. Otherwise, crete a new one.
        figsize : tuple, optional
            Width, height in inches. Format: (float, float).
        kwargs
            Other keyword arguments will be passed down to
            :meth:`pandas.DataFrame.plot.bar`.

        Returns
        -------
        matplotlib.axes.Axes
            The matplotlib axes containing the plot.

        Examples
        --------
        Below is a simple example:

        .. plot::

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> maf_file = '~/fuc-data/tcga-laml/tcga_laml.maf.gz'
            >>> mf = pymaf.MafFrame.from_file(maf_file)
            >>> mf.plot_tmb(width=1)
            >>> plt.tight_layout()
        """
        df = self.matrix_tmb()
        if samples is not None:
            df = df.loc[samples]
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        df.plot.bar(stacked=True, ax=ax, width=width, legend=False,
            color=NONSYN_COLORS, **kwargs)
        ax.set_xlabel('Samples')
        ax.set_ylabel('Count')
        ax.set_xticks([])
        return ax

    def plot_vaf(
        self, col, count=10, af=None, hue=None, hue_order=None,
        flip=False, ax=None, figsize=None, **kwargs
    ):
        """
        Create a box plot showing the VAF distributions of top mutated genes.

        A grouped box plot can be created with ``hue`` (requires an
        AnnFrame).

        Parameters
        ----------
        col : str
            Column in the MafFrame containing VAF data.
        count : int, default: 10
            Number of top mutated genes to display.
        af : AnnFrame, optional
            AnnFrame containing sample annotation data.
        hue : str, optional
            Column in the AnnFrame containing information about sample groups.
        hue_order : list, optional
            Order to plot the group levels in.
        flip : bool, default: False
            If True, flip the x and y axes.
        ax : matplotlib.axes.Axes, optional
            Pre-existing axes for the plot. Otherwise, crete a new one.
        figsize : tuple, optional
            Width, height in inches. Format: (float, float).
        kwargs
            Other keyword arguments will be passed down to
            :meth:`seaborn.boxplot`.

        Returns
        -------
        matplotlib.axes.Axes
            The matplotlib axes containing the plot.

        Examples
        --------

        Below is a simple example:

        .. plot::
            :context: close-figs

            >>> import matplotlib.pyplot as plt
            >>> from fuc import common, pymaf
            >>> common.load_dataset('tcga-laml')
            >>> maf_file = '~/fuc-data/tcga-laml/tcga_laml.maf.gz'
            >>> mf = pymaf.MafFrame.from_file(maf_file)
            >>> mf.plot_vaf('i_TumorVAF_WU')
            >>> plt.tight_layout()

        We can create a grouped bar plot based on FAB classification:

        .. plot::
            :context: close-figs

            >>> annot_file = '~/fuc-data/tcga-laml/tcga_laml_annot.tsv'
            >>> af = pymaf.AnnFrame.from_file(annot_file)
            >>> mf.plot_vaf('i_TumorVAF_WU',
            ...             af=af,
            ...             hue='FAB_classification',
            ...             hue_order=['M1', 'M2', 'M3'],
            ...             count=5)
            >>> plt.tight_layout()
        """
        medians = self.df.groupby('Hugo_Symbol')[col].median()
        top_genes = self.matrix_genes(count=count).index.to_list()
        sorted_genes = medians[top_genes].sort_values(
            ascending=False).index.to_list()

        df = self.df[self.df.Hugo_Symbol.isin(sorted_genes)]

        if hue is not None:
            df = pd.merge(df, af.df, left_on='Tumor_Sample_Barcode',
                right_index=True)

        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)

        if flip:
            x, y = col, 'Hugo_Symbol'
            xlabel, ylabel = 'VAF', ''
        else:
            x, y = 'Hugo_Symbol', col
            xlabel, ylabel = '', 'VAF'

        sns.boxplot(x=x, y=y, data=df, ax=ax, order=sorted_genes,
            hue=hue, hue_order=hue_order, **kwargs)

        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)

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
        sns.barplot(x='Count', y='Variant_Classification', data=df,
                    ax=ax, palette=NONSYN_COLORS, **kwargs)
        ax.set_ylabel('')
        return ax

    def plot_varsum(self, flip=False, ax=None, figsize=None):
        """Create a summary box plot for variant classifications.

        Parameters
        ----------
        flip : bool, default: False
            If True, flip the x and y axes.
        ax : matplotlib.axes.Axes, optional
            Pre-existing axes for the plot. Otherwise, crete a new one.
        figsize : tuple, optional
            Width, height in inches. Format: (float, float).

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
            >>> mf.plot_varsum()
            >>> plt.tight_layout()
        """
        df = self.matrix_tmb()
        df = pd.melt(df, value_vars=df.columns)
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        if flip:
            x, y = 'variable', 'value'
            xlabel, ylabel = '', 'Samples'
        else:
            x, y = 'value', 'variable'
            xlabel, ylabel = 'Samples', ''
        sns.boxplot(x=x, y=y, data=df, ax=ax, showfliers=False,
            palette=NONSYN_COLORS)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
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
        sns.barplot(x='Variant_Type', y='index', data=df, ax=ax,
            palette='pastel', **kwargs)
        ax.set_xlabel('Count')
        ax.set_ylabel('')
        return ax

    def plot_waterfall(
        self, count=10, keep_empty=False, samples=None, ax=None, figsize=None, **kwargs
    ):
        """
        Create a waterfall plot.

        See the :ref:`tutorials:Create customized oncoplots` tutorial to
        learn how to create customized oncoplots.

        Parameters
        ----------
        count : int, default: 10
            Number of top mutated genes to display.
        keep_empty : bool, default: False
            If True, display samples that do not have any mutations.
        samples : list, optional
            List of samples to display.
        ax : matplotlib.axes.Axes, optional
            Pre-existing axes for the plot. Otherwise, crete a new one.
        figsize : tuple, optional
            Width, height in inches. Format: (float, float).
        kwargs
            Other keyword arguments will be passed down to
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
            >>> mf.plot_waterfall(linewidths=0.5)
            >>> plt.tight_layout()
        """
        df = self.matrix_waterfall(count=count, keep_empty=keep_empty)

        if samples is not None:
            df = df[samples]

        # Apply the mapping between items and integers.
        l = reversed(NONSYN_NAMES + ['Multi_Hit', 'None'])
        d = {k: v for v, k in enumerate(l)}
        df = df.applymap(lambda x: d[x])

        # Plot the heatmap.
        if ax is None:
            fig, ax = plt.subplots(figsize=figsize)
        colors = list(reversed(NONSYN_COLORS + ['k', 'lightgray']))
        sns.heatmap(df, cmap=colors, ax=ax, xticklabels=False,
            cbar=False, **kwargs)
        ax.set_xlabel('Samples')
        ax.set_ylabel('')

        return ax

    def to_vcf(
        self, fasta=None, ignore_indels=False, cols=None, names=None
    ):
        """
        Write the MafFrame to a VcfFrame.

        Converting from MAF to VCF is pretty straightforward for SNVs, but it
        can be challenging for INDELs and complex events involving multiple
        nucleotides (e.g. 'AAGG' → 'CCCG'). This is because, for the latter
        case we need to identify the "anchor" nucleotide for each event,
        which is crucial for constructing a properly formatted VCF. For
        example, a deletion event 'AGT' → '-' in MAF would have to be
        converted to 'CAGT' → 'C' in the VCF where 'C' is our anchor
        nucleotide. The position should be shifted by one as well.

        In order to tackle this issue, the method makes use of a reference
        assembly (i.e. FASTA file). If SNVs are your only concern, then you
        do not need a FASTA file and can just set ``ignore_indels`` as True.
        If you are going to provide a FASTA file, please make sure to select
        the appropriate one (e.g. one that matches the genome assembly). For
        example, if your MAF is in hg19/GRCh37, use the 'hs37d5.fa' file
        which can be freely downloaded from the 1000 Genomes Project.

        Parameters
        ----------
        fasta : str, optional
            FASTA file. Required if ``ignore_indels`` is False.
        ignore_indels : bool, default: False
            If True, do not include INDELs in the VcfFrame. Useful when
            a FASTA file is not available.
        cols : str or list, optional
            Column(s) in the MafFrame which contain additional genotype
            data of interest. If provided, these data will be added to
            individual sample genotypes (e.g. '0/1:0.23').
        names : str or list, optional
            Name(s) to be displayed in the FORMAT field (e.g. AD, AF, DP).
            If not provided, the original column name(s) will be displayed.

        Returns
        -------
        VcfFrame
            The VcfFrame object.

        Examples
        --------

        >>> from fuc import pymaf
        >>> mf = pymaf.MafFrame.from_file('in.maf')
        >>> vf = mf.to_vcf(fasta='hs37d5.fa')
        >>> vf = mf.to_vcf(ignore_indels=True)
        >>> vf = mf.to_vcf(fasta='hs37d5.fa', cols='i_TumorVAF_WU', names='AF')
        """
        if not ignore_indels and fasta is None:
            raise ValueError("A FASTA file is required when 'ignore_indels' "
                             "argument is False.")

        if cols is None:
            cols = []
        if names is None:
            names = []

        if isinstance(cols, str):
            cols = [cols]
        if isinstance(names, str):
            names = [names]

        if cols and not names:
            names = cols
        if len(cols) != len(names):
            raise ValueError("Arguments 'cols' and 'names' "
                             "have different lengths.")

        # Create the minimal VCF.
        index_cols = ['Chromosome', 'Start_Position',
                      'Reference_Allele', 'Tumor_Seq_Allele2']
        df = self.df.pivot(index=index_cols,
                           columns='Tumor_Sample_Barcode',
                           values='Tumor_Seq_Allele2')
        f = lambda x: '0/0' if pd.isnull(x) else '0/1'
        df = df.applymap(f)
        df.columns.name = None
        df = df.reset_index()
        df = df.rename(columns={'Chromosome': 'CHROM',
                                'Start_Position': 'POS',
                                'Reference_Allele': 'REF',
                                'Tumor_Seq_Allele2': 'ALT'})
        df['ID'] = '.'
        df['QUAL'] = '.'
        df['FILTER'] = '.'
        df['INFO'] = '.'
        df['FORMAT'] = 'GT'
        df = df[pyvcf.HEADERS + self.samples]

        # Add requested genotype information.
        f = lambda x: '.' if pd.isnull(x) else str(x)
        for i, col in enumerate(cols):
            _ = self.df.pivot(index=index_cols,
                              columns='Tumor_Sample_Barcode',
                              values='i_TumorVAF_WU')
            _ = _.reset_index()
            _ = _.drop(index_cols, axis=1)
            _ = _[self.samples]
            _ = _.applymap(f)
            df.iloc[:, 9:] = df.iloc[:, 9:] + ':' + _
            df.FORMAT = df.FORMAT + ':' + names[i]

        # Handle INDELs.
        l = ['A', 'C', 'G', 'T']
        if ignore_indels:
            i = (df.REF.isin(l)) & (df.ALT.isin(l))
            df = df[i]
        else:
            def one_row(r):
                if r.REF in l and r.ALT in l:
                    return r
                region = f'{r.CHROM}:{r.POS-1}-{r.POS-1}'
                anchor = common.extract_sequence(fasta, region)
                if not anchor:
                    return r
                r.POS = r.POS - 1
                if r.ALT == '-':
                    r.REF = anchor + r.REF
                    r.ALT = anchor
                elif r.REF == '-':
                    r.REF = anchor
                    r.ALT = anchor + r.ALT
                else:
                    r.REF = anchor + r.REF
                    r.ALT = anchor + r.ALT
                return r
            df = df.apply(one_row, axis=1)

        # Create the metadata.
        meta = [
            '##fileformat=VCFv4.3',
            '##source=fuc.api.pymaf.MafFrame.to_vcf',
        ]

        # Create the VcfFrame.
        vf = pyvcf.VcfFrame(meta, df)

        return vf

    def to_file(self, fn):
        """Write MafFrame to a MAF file.

        Parameters
        ----------
        fn : str
            MAF file path.
        """
        with open(fn, 'w') as f:
            f.write(self.to_string())

    def to_string(self):
        """Render MafFrame to a console-friendly tabular output.

        Returns
        -------
        str
            String representation of MafFrame.
        """
        return self.df.to_csv(index=False, sep='\t')

    def filter_annot(self, af, expr):
        """
        Filter the MafFrame using sample annotation data.

        Samples are selected by querying the columns of an AnnFrame with a
        boolean expression. Samples not present in the MafFrame will be
        excluded automatically.

        Parameters
        ----------
        af : AnnFrame
            AnnFrame with sample annotaton data.
        expr : str
            Query expression to evaluate.

        Returns
        -------
        MafFrame
            Filtered MafFrame.

        Examples
        --------

        >>> from fuc import common, pymaf
        >>> common.load_dataset('tcga-laml')
        >>> mf = pymaf.MafFrame.from_file('~/fuc-data/tcga-laml/tcga_laml.maf.gz')
        >>> af = pymaf.AnnFrame.from_file('~/fuc-data/tcga-laml/tcga_laml_annot.tsv')
        >>> filtered_mf = mf.filter_annot(af, "FAB_classification == 'M4'")
        """
        samples = af.df.query(expr).index
        i = self.df.Tumor_Sample_Barcode.isin(samples)
        df = self.df[i]
        mf = self.__class__(df)
        return mf
