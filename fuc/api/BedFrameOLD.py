"""
The BedFrame module is designed for working with BED files. For example,
it can be used to find the intersection between multiple BED files.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from copy import deepcopy

@dataclass(unsafe_hash=True)
class BedRecord:
    """Class for storing the information of single BED record.

    This class strictly sticks to the BED format described in the UCSC
    Genome Browser (https://genome.ucsc.edu/FAQ/FAQformat.html).

    BED lines have three required fields and nine additional optional fields:
         1. chrom (required) - The name of the chromosome.
         2. chromStart (required) - The starting position of the feature.
         3. chromEnd (required) - The ending position of the feature.
         4. name (optional) - Defines the name of the BED line.
         5. score (optional) - A score between 0 and 1000 for color density.
         6. strand (optional) - Either "." (=no strand) or "+" or "-".
         7. thickStart (optional) - The starting position for thick drawing.
         8. thickEnd (optional) - The ending position for thick drawing.
         9. itemRgb (optional) - An RGB value (e.g. 255,0,0).
        10. blockCount (optional) - The number of blocks (exons).
        11. blockSizes (optional) - A comma-separated list of the block sizes.
        12. blockStarts (optional) - A comma-separated list of block starts.
    """
    chrom   : str  = field(compare=True)
    start   : int  = field(compare=True)
    end     : int  = field(compare=True)
    name    : Optional[str] = field(default=None, compare=False)
    score   : Optional[int] = field(default=None, compare=False)
    strand  : Optional[str] = field(default=None, compare=False)
    tstart  : Optional[int] = field(default=None, compare=False)
    tend    : Optional[int] = field(default=None, compare=False)
    itemrgb : Optional[List[int]] = field(default=None, compare=False)
    bcount  : Optional[int] = field(default=None, compare=False)
    bsizes  : Optional[List[int]] = field(default=None, compare=False)
    bstarts : Optional[List[int]] = field(default=None, compare=False)

    def __eq__(self, other):
        """Test whether two BedRecords are equal."""
        return (self.chrom, self.start, self.end) == (
            other.chrom, other.start, other.end)

    def to_list(self):
        """Convert the BedRecord to a list of strings."""
        l = [self.chrom, str(self.start), str(self.end)]
        if self.name is not None: l.append(self.name)
        if self.score is not None: l.append(str(self.score))
        if self.strand is not None: l.append(self.strand)
        if self.tstart is not None: l.append(str(self.tstart))
        if self.tend is not None: l.append(str(self.tend))
        if self.itemrgb is not None: l.append(','.join(self.itemrgb))
        if self.bcount is not None: l.append(str(self.bcount))
        if self.bsizes is not None: l.append(','.join(self.bsizes))
        if self.bstarts is not None: l.append(','.join(self.bstarts))
        return l

    @classmethod
    def from_list(cls, l):
        """Create a BedRecord from a list of strings."""
        f = lambda s: [int(x) for x in s.split(',')]
        l[1] = int(l[1])                  # chromStart
        l[2] = int(l[2])                  # chromEnd
        if len(l) == 5: l[4] = int(l[4])  # score
        if len(l) == 7: l[6] = int(l[6])  # thickStart
        if len(l) == 8: l[7] = int(l[7])  # thickEnd
        if len(l) == 9: f(l[8])           # itemRgb
        if len(l) == 10: l[9] = int(l[9]) # blockCount
        if len(l) == 11: f(l[10])         # blockSizes
        if len(l) == 12: f(l[11])         # blockStarts
        r = cls(*l)
        return r

@dataclass
class BedFrame:
    """Class for storing the information of single BED file."""
    meta : List[str]
    data : List[BedRecord]

    @property
    def vmeta(self):
        """Return a view (copy) of the metadata."""
        return deepcopy(self.meta)

    @property
    def vdata(self):
        """Return a view (copy) of the data."""
        return deepcopy(self.data)

    @property
    def shape(self):
        """Return the size of the BedFrame."""
        return len(self.data)

    def to_file(self, file_path):
        """Write the BedFrame to a file."""
        with open(file_path, 'w') as f:
            if self.meta:
                f.write('\n'.join(self.meta) + '\n')
            for r in self.data:
                f.write('\t'.join(r.to_list()) + '\n')

    @classmethod
    def from_file(cls, file_path):
        """Create a BedFrame from a file."""
        meta = []
        data = []
        with open(file_path) as f:
            for line in f:
                fields = line.strip().split('\t')
                print(fields)
                if len(fields) < 3:
                    meta = line.strip()
                    continue
                data.append(BedRecord.from_list(fields))
        bf = cls(meta, data)
        return bf

    def intersect(self, other):
        """Find the intersection between the two BedFrames.

        Metadata and optional BED fields in the other BedFrame
        will be ignored.

        Parameters
        ----------
        other : BedFrame
            Other BedFrame.

        Returns
        -------
        bf: BedFrame
            New BedFrame.
        """
        def overlap(a, b):
            if b[0] <= a[0] <= b[1]:
                start = a[0]
            elif a[0] <= b[0] <= a[1]:
                start = b[0]
            else:
                return None
            if b[0] <= a[1] <= b[1]:
                end = a[1]
            elif a[0] <= b[1] <= a[1]:
                end = b[1]
            else:
                return None
            return (start, end)
        meta = self.vmeta
        data = []
        for r1 in self.vdata:
            for r2 in other.vdata:
                if r1.chrom != r2.chrom:
                    continue
                result = overlap((r1.start, r1.end), (r2.start, r2.end))
                if result is not None:
                    r3 = deepcopy(r1)
                    r3.start = result[0]
                    r3.end = result[1]
                    data.append(r3)
        bf = self.__class__(meta, data)
        return bf
