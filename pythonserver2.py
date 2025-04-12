from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import subprocess  # More secure than os.popen2
from typing import List, Type  # For type hints

class ServerException(Exception):
    """Custom exception for server errors."""
    pass

class BaseCase:
    """Parent for all case handlers with common functionality."""
    
    def handle_file(self, handler: 'RequestHandler', full_path: str) -> None:
        try:
            with open(full_path, 'rb') as reader:
                content = reader.read()
            handler.send_content(content)
        except IOError as msg:
            msg = f"'{full_path}' cannot be read: {msg}"
            handler.handle_error(msg)

    def index_path(self, handler: 'RequestHandler') -> str:
        return os.path.join(handler.full_path, 'index.html')

    def test(self, handler: 'RequestHandler') -> bool:
        raise NotImplementedError('Subclasses must implement this method')

    def act(self, handler: 'RequestHandler') -> None:
        raise NotImplementedError('Subclasses must implement this method')

class CaseNoFile(BaseCase):
    """File or directory does not exist."""
    
    def test(self, handler: 'RequestHandler') -> bool:
        return not os.path.exists(handler.full_path)

    def act(self, handler: 'RequestHandler') -> None:
        raise ServerException(f"'{handler.path}' not found")

class CaseExistingFile(BaseCase):
    """File exists."""
    
    def test(self, handler: 'RequestHandler') -> bool:
        return os.path.isfile(handler.full_path)

    def act(self, handler: 'RequestHandler') -> None:
        handler.handle_file(handler.full_path)

class CaseDirectoryIndexFile(BaseCase):
    """Serve index.html page for a directory."""
    
    def test(self, handler: 'RequestHandler') -> bool:
        return os.path.isdir(handler.full_path) and \
               os.path.isfile(self.index_path(handler))

    def act(self, handler: 'RequestHandler') -> None:
        handler.handle_file(self.index_path(handler))

class CaseDirectoryNoIndexFile(BaseCase):
    """Serve listing for a directory without an index.html page."""
    
    def test(self, handler: 'RequestHandler') -> bool:
        return os.path.isdir(handler.full_path) and \
               not os.path.isfile(self.index_path(handler))

    def act(self, handler: 'RequestHandler') -> None:
        handler.list_dir(handler.full_path)

class CaseCGIFile(BaseCase):
    """Execute CGI scripts."""
    
    def test(self, handler: 'RequestHandler') -> bool:
        return os.path.isfile(handler.full_path) and \
               handler.full_path.endswith('.py')

    def act(self, handler: 'RequestHandler') -> None:
        handler.run_cgi(handler.full_path)

class CaseAlwaysFail(BaseCase):
    """Base case if nothing else worked."""
    
    def test(self, handler: 'RequestHandler') -> bool:
        return True

    def act(self, handler: 'RequestHandler') -> None:
        raise ServerException(f"Unknown object '{handler.path}'")

class RequestHandler(BaseHTTPRequestHandler):
    """
    Handle HTTP requests by returning files or directory listings.
    If anything goes wrong, an error page is constructed.
    """
    
    # Define the processing pipeline
    CASES: List[BaseCase] = [
        CaseNoFile(),
        CaseExistingFile(),
        CaseDirectoryIndexFile(),
        CaseDirectoryNoIndexFile(),
        CaseCGIFile(),
        CaseAlwaysFail()
    ]
    
    # Template for error pages
    ERROR_PAGE = """\
<html>
<head><title>Error accessing {path}</title></head>
<body>
<h1>Error accessing {path}</h1>
<p>{msg}</p>
</body>
</html>"""
    
    # Template for directory listings
    LISTING_PAGE = """\
<html>
<head><title>Directory listing for {path}</title></head>
<body>
<h2>Directory listing for {path}</h2>
<hr>
<ul>
{items}
</ul>
<hr>
</body>
</html>"""
    
    # Template for the root page
    ROOT_PAGE = """\
<html>
<head><title>Server Info</title></head>
<body>
<h1>Server Information</h1>
<table border="1">
<tr><th>Header</th><th>Value</th></tr>
<tr><td>Date and time</td><td>{date_time}</td></tr>
<tr><td>Client host</td><td>{client_host}</td></tr>
<tr><td>Client port</td><td>{client_port}</td></tr>
<tr><td>Command</td><td>{command}</td></tr>
<tr><td>Path</td><td>{path}</td></tr>
</table>
</body>
</html>"""
    
    def do_GET(self) -> None:
        """Handle GET requests."""
        try:
            if self.path == "/":
                self.send_root_page()
                return
            
            # Resolve the full filesystem path
            self.full_path = os.path.abspath(os.getcwd() + self.path)
            
            # Security check: prevent directory traversal
            if not self.full_path.startswith(os.getcwd()):
                raise ServerException("Attempted directory traversal")
            
            # Process the request through the case handlers
            for case in self.CASES:
                if case.test(self):
                    case.act(self)
                    break
                    
        except ServerException as msg:
            self.handle_error(str(msg), 404)
        except Exception as e:
            self.handle_error(f"Internal server error: {str(e)}", 500)
    
    def do_POST(self) -> None:
        """Handle POST requests."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            
            # Process the POST data (example only - add your logic here)
            response = b"Received: " + post_data
            
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        except Exception as e:
            self.handle_error(f"Error processing POST: {str(e)}", 500)
    
    def send_root_page(self) -> None:
        """Generate and send the root info page."""
        values = {
            'date_time': self.date_time_string(),
            'client_host': self.client_address[0],
            'client_port': self.client_address[1],
            'command': self.command,
            'path': self.path
        }
        page = self.ROOT_PAGE.format(**values).encode('utf-8')
        self.send_content(page)
    
    def handle_file(self, full_path: str) -> None:
        """Handle file requests with proper MIME types."""
        try:
            with open(full_path, 'rb') as f:
                content = f.read()
            
            # Simple MIME type detection
            if full_path.endswith(".html"):
                content_type = "text/html"
            elif full_path.endswith(".css"):
                content_type = "text/css"
            elif full_path.endswith(".js"):
                content_type = "application/javascript"
            elif full_path.endswith(".png"):
                content_type = "image/png"
            elif full_path.endswith(".jpg") or full_path.endswith(".jpeg"):
                content_type = "image/jpeg"
            else:
                content_type = "text/plain"
            
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except IOError:
            raise ServerException(f"Cannot read file: {full_path}")
    
    def list_dir(self, full_path: str) -> None:
        """Generate directory listing."""
        try:
            entries = sorted(os.listdir(full_path))
            items = []
            
            for entry in entries:
                if not entry.startswith('.'):  # Skip hidden files
                    link = os.path.join(self.path, entry)
                    items.append(f'<li><a href="{link}">{entry}</a></li>')
            
            page = self.LISTING_PAGE.format(
                path=self.path,
                items='\n'.join(items)
            ).encode('utf-8')
            
            self.send_content(page)
        except OSError as msg:
            raise ServerException(f"'{self.path}' cannot be listed: {msg}")
    
    def run_cgi(self, full_path: str) -> None:
        """Execute CGI scripts securely."""
        try:
            # Use subprocess for better security than os.popen2
            result = subprocess.run(
                ['python', full_path],
                capture_output=True,
                text=True,
                check=True
            )
            self.send_content(result.stdout.encode('utf-8'))
        except subprocess.CalledProcessError as e:
            self.handle_error(f"CGI script error: {e.stderr}", 500)
        except Exception as e:
            self.handle_error(f"Error running CGI: {str(e)}", 500)
    
    def handle_error(self, msg: str, status: int = 404) -> None:
        """Send error page with appropriate status code."""
        page = self.ERROR_PAGE.format(
            path=self.path,
            msg=msg
        ).encode('utf-8')
        
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(page)))
        self.end_headers()
        self.wfile.write(page)
    
    def send_content(self, content: bytes, status: int = 200) -> None:
        """Send content with proper headers."""
        self.send_response(status)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

if __name__ == '__main__':
    server_address = ('localhost', 8000)
    server = HTTPServer(server_address, RequestHandler)
    print(f"Serving on http://{server_address[0]}:{server_address[1]}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.server_close()