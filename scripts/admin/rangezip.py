import io, sys, urllib.request, zipfile, json

class HTTPRangeFile(io.RawIOBase):
    def __init__(self, url):
        self.url = url
        self.pos = 0
        req = urllib.request.Request(url, headers={"Range": "bytes=0-0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            cr = r.headers["Content-Range"]  # e.g. bytes 0-0/1058477546
            self.size = int(cr.split("/")[-1])
            self.url = r.geturl()  # final signed S3 URL after redirect
            r.read()
    def readable(self): return True
    def seekable(self): return True
    def seek(self, off, whence=0):
        if whence == 0: self.pos = off
        elif whence == 1: self.pos += off
        else: self.pos = self.size + off
        return self.pos
    def tell(self): return self.pos
    def read(self, n=-1):
        if n is None or n < 0:
            end = self.size - 1
        else:
            end = min(self.pos + n - 1, self.size - 1)
        if self.pos > end:
            return b""
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        with urllib.request.urlopen(req, timeout=600) as r:
            data = r.read()
        self.pos += len(data)
        return data
    def readinto(self, b):
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)

if __name__ == "__main__":
    url = sys.argv[1]
    f = HTTPRangeFile(url)
    z = zipfile.ZipFile(f)
    for i in z.infolist():
        print(i.filename, i.file_size, i.compress_size)
