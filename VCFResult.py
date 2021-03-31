import copy

VCF_HEADERS = (
    '#CHROM', 'POS', 'ID',
    'REF', 'ALT', 'QUAL',
    'FILTER', 'INFO', 'FORMAT'
)

class VCFResult():
    def __init__(self):
        self.meta = []
        self.head = VCF_HEADERS
        self.data = {}

    @property
    def samples(self):
        """Return a list of sample IDs."""
        return self.head[9:]

    @property
    def shape(self):
        """Return a tuple representing the dimensionality of the VCFResult."""
        return (len(self.head[9:]), len(self.data))

    def write(self, vcf_path):
        """Write the VCFResult to a file."""
        with open(vcf_path, 'w') as f:
            f.write(''.join(self.meta))
            f.write('\t'.join(self.head) + '\n')
            for record, fields in self.data.items():
                f.write('\t'.join(fields) + '\n')

    def describe(self):
        """Generate descriptive statistics."""
        print('Samples:')
        print('Name', 'VariantCount')
        for i, name in enumerate(self.samples):
            n = 0
            for record, fields in self.data.items():
                if '1' in fields[i+9].split(':')[0]:
                    n += 1
            print(name, n)

    def strip(self, subfields=None):
        """Return a stripped VCFResult."""
        vcf_result = self.__class__()
        vcf_result.head = copy.deepcopy(self.head)
        for record, fields in self.data.items():
            fields[2] = '.'
            fields[6] = '.'
            fields[7] = '.'
            if subfields is None:
                _subfields = ['GT']
            else:
                _subfields = ['GT'] + subfields
            index_list = []
            for subfield in _subfields:
                i = fields[8].split(':').index(subfield)
                index_list.append(i)
            fields[8] = ':'.join(_subfields)
            fields[9:] = [':'.join([x.split(':')[i] for i in index_list])
                for x in fields[9:]]
            vcf_result.data[record] = fields
        return vcf_result

    def merge(self, other, subfields=None):
        """Return a merged VCFResult."""
        vcf1 = self.strip(subfields=subfields)
        vcf2 = other.strip(subfields=subfields)
        vcf3 = VCFResult()
        vcf3.head = vcf1.head + vcf2.head[9:]
        missing = './.'
        record, fields = next(iter(vcf2.data.items()))
        n = len(fields[8].split(':'))
        for i in range(1, n):
            missing += ':.'
        for record, fields in vcf1.data.items():
            if record in vcf2.data:
                vcf3.data[record] = fields
            else:
                fields = fields + [missing] * vcf2.shape[0]
                vcf3.data[record] = fields
        for record, fields in vcf2.data.items():
            if record in vcf3.data:
                vcf3.data[record] += fields[9:]
            else:
                fields = fields[:9] + [missing] * vcf1.shape[0] + fields[9:]
                vcf3.data[record] = fields
        return vcf3

    def add_dp(self):
        """Return a new VCFResult with the DP subfield."""
        vcf_result = self.__class__()
        vcf_result.head = copy.deepcopy(self.head)
        def func(x, i):
            ad = x.split(':')[i].split(',')
            dp = 0
            for depth in ad:
                if depth == '.':
                    return f'{x}:.'
                dp += int(depth)
            return f'{x}:{dp}'
        for record, fields in self.data.items():
            i = fields[8].split(':').index('AD')
            fields[9:] = [func(x, i) for x in fields[9:]]
            fields[8] += ':DP'
            vcf_result.data[record] = fields
        return vcf_result

    def filter_dp(self, threshold=200):
        """Return a new VCFResult filtered based on the DP subfield."""
        vcf_result = self.__class__()
        vcf_result.head = copy.deepcopy(self.head)
        def func(x, i):
            l = x.split(':')
            dp = l[i]
            if dp == '.' or int(dp) < threshold:
                return './.' + ':.' * (len(l)-1)
            return x
        for record, fields in self.data.items():
            i = fields[8].split(':').index('DP')
            fields[9:] = [func(x, i) for x in fields[9:]]
            vcf_result.data[record] = fields
        return vcf_result

    def filter_af(self, threshold=0.1):
        """Return a new VCFResult filtered based on the AF subfield."""
        vcf_result = self.__class__()
        vcf_result.head = copy.deepcopy(self.head)
        def func(x, i):
            l = x.split(':')
            af = l[i]
            if af == '.' or float(af) < threshold:
                return './.' + ':.' * (len(l)-1)
            return x
        for record, fields in self.data.items():
            i = fields[8].split(':').index('AF')
            fields[9:] = [func(x, i) for x in fields[9:]]
            vcf_result.data[record] = fields
        return vcf_result

    def remove_empty(self):
        """Return a new VCFResult after removing empty records."""
        vcf_result = self.__class__()
        vcf_result.head = copy.deepcopy(self.head)
        for record, fields in self.data.items():
            if all(['.' in x.split(':')[0] for x in fields[9:]]):
                continue
            vcf_result.data[record] = fields
        return vcf_result

    def update(self, other, names):
        """Copy data from another VCFResult.

        This method will copy requested data from another VCFResult for
        overlapping records. You can only request data from the following
        VCF headers: ID, QUAL, FILTER, INFO, and FORMAT. Any other
        requested VCF headers will be ignored.

        Parameters
        ----------
        other : VCFResult
            Target VCFResult.
        names : list
            List of VCF headers.

        Returns
        -------
        vcf_result : VCFResult
            Updated VCFResult.
        """
        vcf_result = self.__class__()
        vcf_result.head = copy.deepcopy(self.head)
        targets = ['ID', 'QUAL', 'FILTER', 'INFO', 'FORMAT']
        names = [x for x in names if x in targets]
        indicies = [VCF_HEADERS.index(x) for x in names]
        for record, fields1 in self.data.items():
            if record in other.data:
                fields2 = other.data[record]
                for i in indicies:
                    fields1[i] = fields2[i]
            vcf_result.data[record] = fields1
        return vcf_result

    def apply(self, name, func):
        """Apply the given function and return a new VCFResult."""
        i = VCF_HEADERS.index(name)
        vcf_result = self.__class__()
        for record, fields in self.data.items():
            fields[i] = func(fields[i])
            vcf_result.data[record] = fields
        return vcf_result

    @classmethod
    def read(cls, vcf_path):
        """Create a VCFResult from a file."""
        vcf_result = cls()
        with open(vcf_path) as f:
            for line in f:
                if line.startswith('##'):
                    vcf_result.meta.append(line)
                elif line.startswith('#CHROM'):
                    fields = line.strip().split('\t')
                    vcf_result.head = fields
                else:
                    fields = line.strip().split('\t')
                    record = '{}:{}:{}:{}'.format(fields[0], fields[1],
                        fields[3], fields[4])
                    vcf_result.data[record] = fields
        return vcf_result
