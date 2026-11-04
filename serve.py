import os
import re
import sys
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler


class RangeHTTPRequestHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler with HTTP Range (byte-range) support for media seeking."""

    def end_headers(self):
        self.send_header("Accept-Ranges", "bytes")
        super().end_headers()

    def send_head(self):
        """Send response code and MIME headers, returning file handle or None."""
        path = self.translate_path(self.path)
        if os.path.isdir(path):
            parts = self.path.split("?", 1)
            if not parts[0].endswith("/"):
                self.send_response(HTTPStatus.MOVED_PERMANENTLY)
                new_parts = (parts[0] + "/",) + tuple(parts[1:])
                new_url = "?".join(new_parts)
                self.send_header("Location", new_url)
                self.end_headers()
                return None
            for index in ("index.html", "index.htm"):
                index_path = os.path.join(path, index)
                if os.path.exists(index_path):
                    path = index_path
                    break
            else:
                return super().send_head()

        ctype = self.guess_type(path)
        try:
            f = open(path, "rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None

        try:
            fs = os.fstat(f.fileno())
            file_len = fs[6]

            range_header = self.headers.get("Range")
            if range_header and range_header.startswith("bytes="):
                ranges = range_header[6:].strip()
                match = re.match(r"^(\d*)-(\d*)$", ranges)
                if match:
                    start_str, end_str = match.groups()
                    if start_str and end_str:
                        start = int(start_str)
                        end = int(end_str)
                    elif start_str:
                        start = int(start_str)
                        end = file_len - 1
                    elif end_str:
                        start = max(0, file_len - int(end_str))
                        end = file_len - 1
                    else:
                        start = 0
                        end = file_len - 1

                    if start > end or start >= file_len:
                        self.send_error(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                        self.send_header("Content-Range", f"bytes */{file_len}")
                        self.end_headers()
                        f.close()
                        return None

                    end = min(end, file_len - 1)
                    content_length = end - start + 1

                    self.send_response(HTTPStatus.PARTIAL_CONTENT)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Range", f"bytes {start}-{end}/{file_len}")
                    self.send_header("Content-Length", str(content_length))
                    self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
                    self.end_headers()

                    f.seek(start)
                    self.range_to_send = content_length
                    return f

            # Normal full content response
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(file_len))
            self.send_header("Last-Modified", self.date_time_string(fs.st_mtime))
            self.end_headers()
            self.range_to_send = file_len
            return f
        except Exception:
            f.close()
            raise

    def copyfile(self, source, outputfile):
        """Copy all or requested byte range from source to outputfile."""
        bytes_to_send = getattr(self, "range_to_send", None)
        if bytes_to_send is None:
            super().copyfile(source, outputfile)
            return

        bufsize = 64 * 1024
        while bytes_to_send > 0:
            read_size = min(bufsize, bytes_to_send)
            buf = source.read(read_size)
            if not buf:
                break
            try:
                outputfile.write(buf)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                break
            bytes_to_send -= len(buf)

    def log_message(self, format, *args):
        # Concise logging
        sys.stderr.write(f"[{self.log_date_time_string()}] {self.address_string()} - {format % args}\n")


def run():
    port = 8765
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])

    here = os.path.dirname(os.path.abspath(__file__))
    doc_root = os.path.join(here, "tutorial-site")
    if not os.path.isdir(doc_root):
        doc_root = here

    os.chdir(doc_root)

    server_address = ("127.0.0.1", port)
    httpd = HTTPServer(server_address, RangeHTTPRequestHandler)
    print(f"Serving HTTP on 127.0.0.1 port {port} from {doc_root} with Range support...", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run()

