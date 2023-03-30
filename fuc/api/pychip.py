"""
The pychip submodule is designed for working with annotation or manifest
files from the Axiom (Thermo Fisher Scientific) and Infinium (Illumina)
array platforms.
"""

import re
import pandas as pd

class AxiomFrame:
    """
    Class for storing Axiom annotation data.

    Parameters
    ----------
    meta : list
        List of metadata lines.
    df : pandas.DataFrame
        DataFrame containing annotation data.
    """
    def __init__(self, meta, df):
        self._meta = meta
        self._df = df.reset_index(drop=True)

    @property
    def meta(self):
        """list : List of metadata lines."""
        return self._meta

    @meta.setter
    def meta(self, value):
        self._meta = value

    @property
    def df(self):
        """pandas.DataFrame : DataFrame containing annotation data."""
        return self._df

    @df.setter
    def df(self, value):
        self._df = value.reset_index(drop=True)

    @classmethod
    def from_file(cls, fn):
        """
        Construct AxiomFrame from a CSV file.

        Parameters
        ----------
        fn : str
            CSV file (compressed or uncompressed).

        Returns
        -------
        AxiomFrame
            AxiomFrame object.
        """
        if fn.startswith('~'):
            fn = os.path.expanduser(fn)

        if fn.endswith('.gz'):
            f = gzip.open(fn, 'rt')
        else:
            f = open(fn)

        meta = []
        n = 0
        for line in f:
            if line.startswith('#'):
                meta.append(line)
                n += 1
        f.close()

        df = pd.read_csv(fn, skiprows=n)

        return cls(meta, df)

    def to_vep(self):
        """
        Convert AxiomFrame to the Ensembl VEP format.

        Returns
        -------
        pandas.DataFrame
            Variants in Ensembl VEP format.
        """
        print(self.df.shape)
        df = self.df[self.df.Chromosome != '---']
        print(df.shape)
        def one_row(r):
            result = []
            nucleotides = ['A', 'C', 'G', 'T']
            chrom = r['Chromosome']
            ref = r['Ref Allele']
            strand = r['Strand']
            start = r['Physical Position']
            end = r['Position End']
            for alt in r['Alt Allele'].split(' // '):
                if ref in nucleotides and alt in nucleotides: # SNV
                    pass
                elif alt == '-': # DEL I
                    pass
                elif len(alt) == len(ref): # MNV
                    pass
                elif len(alt) < len(ref) and ref.startswith(alt): # DEL II
                    start += len(alt)
                    ref = ref[len(alt):]
                    alt = '-'
                elif ref == '-': # INS I
                    start += 1
                    end = start - 1
                elif len(alt) > len(ref) and alt.startswith(ref): # INS II
                    diff = len(alt) - len(ref)
                    start += diff
                    end = start - 1
                    ref = '-'
                    alt = alt[diff:]
                else:
                    pass
                line = [chrom, start, end, f'{ref}/{alt}', strand]
                result.append('|'.join([str(x) for x in line]))
            return ','.join(result)
        s = df.apply(one_row, axis=1)
        s = ','.join(s)
        data = [x.split('|') for x in s.split(',')]
        df = pd.DataFrame(data).drop_duplicates()
        df.iloc[:, 1] = df.iloc[:, 1].astype(int)
        df.iloc[:, 2] = df.iloc[:, 2].astype(int)
        df = df.sort_values(by=[0, 1])
        return df

class InfiniumFrame:
    """
    Class for storing Infinium manifest data.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame containing manifest data.
    """
    def __init__(self, df):
        self._df = df.reset_index(drop=True)

    @property
    def df(self):
        """pandas.DataFrame : DataFrame containing manifest data."""
        return self._df

    @df.setter
    def df(self, value):
        self._df = value.reset_index(drop=True)

    @classmethod
    def from_file(cls, fn):
        """
        Construct InfiniumFrame from a CSV file.

        Parameters
        ----------
        fn : str
            CSV file (compressed or uncompressed).

        Returns
        -------
        InfiniumFrame
            InfiniumFrame object.
        """
        if fn.startswith('~'):
            fn = os.path.expanduser(fn)

        if fn.endswith('.gz'):
            f = gzip.open(fn, 'rt')
        else:
            f = open(fn)

        lines = f.readlines()
        f.close()

        for i, line in enumerate(lines):
            if line.startswith('[Assay]'):
                start = i
                headers = lines[i+1].strip().split(',')
            elif line.startswith('[Controls]'):
                end = i

        lines = lines[start+2:end]
        lines = [x.strip().split(',') for x in lines]

        df = pd.DataFrame(lines, columns=headers)

        return cls(df)

    def to_vep(self):
        """
        Convert InfiniumFrame to the Ensembl VEP format.

        Returns
        -------
        pandas.DataFrame
            Variants in Ensembl VEP format.
        """
        df = self.df[(self.df.Chr != 'XY') & (self.df.Chr != '0')]
        def one_row(r):
            pos = r.MapInfo
            matches = re.findall(r'\[([^\]]+)\]', r.SourceSeq)
            if not matches:
                raise ValueError(f'Something went wrong: {r}')
            a1, a2 = matches[0].split('/')
            data = pd.Series([r.Chr, r.MapInfo, a1, a2])
            return data
        df = df.apply(one_row, axis=1)
        return df
