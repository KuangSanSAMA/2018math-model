def convert2binaryStr(a):
    bin_str = bin(a)[2:]
    if len(bin_str) < 8:
        bin_str = '0' * (8-len(bin_str)) + bin_str
    return bin_str

# print(convert2binaryStr(254))