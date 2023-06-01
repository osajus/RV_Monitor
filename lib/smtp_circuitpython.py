# Send an SMTP message with Circuitpython.
# Steven Cogswell March 2023
#
# Based on uMail (MicroMail) for MicroPython Copyright (c) 2018 Shawwwn <shawwwn1@gmai.com> License: MIT
# https://github.com/shawwwn/uMail
#
# Set debug=True in the constructor to enable printing debug messages
# Uses adafruit_binascii (binascii as a builtin) for base64 encoding 
#
# Can't upgrade a socket in circuitpython without a hard crash on ESP32 so STARTTLS connections
# won't work.  use_ssl=True and port 465 will work.   STARTTLS works on pico-w
# https://github.com/adafruit/circuitpython/issues/7314
#
import socketpool
import ssl
from binascii import b2a_base64
import board

DEFAULT_TIMEOUT = 10 # sec
LOCAL_DOMAIN = b'127.0.0.1'
CMD_EHLO = b'EHLO' + b' ' + LOCAL_DOMAIN
CMD_STARTTLS = b'STARTTLS'
CMD_AUTH = b'AUTH'
CMD_MAIL = 'MAIL'
AUTH_PLAIN = b'PLAIN'
AUTH_LOGIN = b'LOGIN'
MAXBUF = 1024

class SMTP:
    """Class to handle sending an SMTP message"""
    def b64(self, b: str):
        """Base64 encoding of a string"""
        self.debug_message("base64 encoding "+b)
        enc = b2a_base64(bytes(b,"utf-8"))[:-1]   # chop off newline
        self.debug_message("base64 encoded as "+str(enc))
        return enc

    def debug_message(self, msg: str):
        """ Print a message if self._debug is set to True"""
        if self._debug:
            print("SMTP: %s" % msg)

    def readline(self):
        """ Read from a socket until an end of line character is read """
        line = b""
        while True:
            self._sock.recv_into(self._buf,1)
            bytesin = self._buf[:1]
            if bytesin == b"\n":
                return line
            line += bytesin

    def cmd(self, cmd: bytes):
        """ Send an SMTP command to the server and receive a response"""
        self.debug_message("Sending %s" % cmd)
        try:
            self._sock.send(b'%s\r\n' % cmd)
        except Exception as e:
            self.debug_message("Exception sending message "+str(e))
            raise e
        self.debug_message("Sent!")
        response = b""
        more=True
        # Read all lines with status codes
        while more:
            # Get 3 bytes (status code)
            self._sock.recv_into(self._buf,3)
            code = self._buf[:3]
            # Get 1 bytes ("-" if there are more status codes pending)
            self._sock.recv_into(self._buf,1)
            if self._buf[:1] != b'-':
                more = False
            # read the remainder of the line up to the newline character
            while True:
                self._sock.recv_into(self._buf,1)
                bytesin = self._buf[:1]
                if bytesin == b'\n':
                    break
                response += bytesin
        self.debug_message("Code: %s Response: %s " % (code, response))
        return code,response

    def __init__(self, host: str=None, port: int=465,
                 pool: socketpool.SocketPool=None, ssl_context: ssl.SSLContext=None, use_ssl: bool=False,
                 username: str=None, password: str=None,
                 debug: bool=False):
        """
        Parameters:
        host: hostname of smtp server
        port: port to connect to on smtp server (465 for SSL, 587 for STARTTLS)
        pool: a socketpool compatible socket
        ssl_conect: a SSLContext compatible ssl context
        use_ssl: start the smtp connection in SSL (does not use STARTTLS)
        username: username used to log into smtp server
        password: password used to log into smtp server
        debug: if True, print smtp transaction messages
        """
        self._debug = debug
        self.username = username
        self._buf = bytearray(MAXBUF)
        self._pool = pool
        self._ssl_context = ssl_context

        self.debug_message(str(self._pool))
        self.debug_message(str(self._ssl_context))

        addr = pool.getaddrinfo(host=host,port=port)[0][-1]
        sock = pool.socket(pool.AF_INET, pool.SOCK_STREAM)
        self.debug_message(host+ " Addr is "+str(addr))

        if use_ssl:
            self.debug_message("Using SSL")
            sock = self._ssl_context.wrap_socket(sock, server_hostname=host)
        else:
            self.debug_message("Not using SSL")
            if "esp32" in board.board_id.lower():
                print("Warning: you will likely get a hard crash trying to use STARTTLS.")
                print("use_ssl=True instead to avoid this issue")
                print("https://github.com/adafruit/circuitpython/issues/7314")
        sock.settimeout(DEFAULT_TIMEOUT)
        sock.connect(addr)

        self._sock = sock
        self.debug_message("got socket")

        # Read connection message status code from smtp server
        self._sock.recv_into(self._buf,3)
        code = self._buf[:3]
        # Read connection message after the status code from smtp server
        self.readline()
        assert code==b"220", 'cant connect to server %s' % (code)
        self.debug_message("Got code %s" % code)

        self.debug_message("Sending EHLO")
        code, resp = self.cmd(CMD_EHLO)
        assert code==b"250", '%d' % code

        if not use_ssl and CMD_STARTTLS in resp:
            self.debug_message("Starting STARTTLS")
            code, resp = self.cmd(CMD_STARTTLS)
            assert code==b"220", 'start tls failed %d, %s' % (code, resp)
            self.debug_message("Wrapping SSL")
            self._sock = self._ssl_context.wrap_socket(sock=self._sock)

        if username and password:
            self.login(username, password)

    def login(self, username, password):
        """ Log into SMTP server (AUTH PLAIN and AUTH LOGIN supported) """
        self.debug_message("Logging in with username %s" % username)
        self.username = username
        code, resp = self.cmd(CMD_EHLO)
        assert code==b"250", '%d, %s' % (code, resp)

        # Determine which AUTH methods are enabled by the smtp server
        auths = None
        ehlo_lines = resp.split(b'\r')
        for line in ehlo_lines:
            if line.startswith(CMD_AUTH):
                auths = line[4:].strip(b' =').split(b' ')
                break
        self.debug_message("AUTH methods are "+str(auths))
        assert auths!=None, "no auth method"

        if AUTH_PLAIN in auths:
            cren_string = "\0%s\0%s" % (username, password)
            cren = self.b64(cren_string)
            code, resp = self.cmd(b'%s %s %s' % (CMD_AUTH, AUTH_PLAIN, cren))
        elif AUTH_LOGIN in auths:
            code, resp = self.cmd(b"%s %s %s" % (CMD_AUTH, AUTH_LOGIN, self.b64(username)))
            assert code==b"334", 'wrong username %d, %s' % (code, resp)
            code, resp = self.cmd(self.b64(password))
        else:
            raise Exception("No valid auth method %s " % auths)

        assert code==b"235" or code==b"503", 'auth error %s, %s' % (code, resp)
        return code, resp

    def to(self, addrs, mail_from=None):
        """ Send TO header to smtp server, addrs can be a list"""
        mail_from = self.username if mail_from==None else mail_from
        code, resp = self.cmd(CMD_EHLO)
        assert code==b'250', '%s' % code
        code, resp = self.cmd(b'MAIL FROM: <%s>' % mail_from.encode("utf-8"))
        assert code==b'250', 'sender refused %s, %s' % (code, resp)

        if isinstance(addrs, str):
            addrs = [addrs]
        count = 0
        for addr in addrs:
            code, resp = self.cmd(b'RCPT TO: <%s>' % addr.encode("utf-8"))
            if code!=b'250' and code!=b'251':
                self.debug_message('%s refused, %s' % (addr, resp))
                count += 1
        assert count!=len(addrs), 'recipient refused, %s, %s' % (code, resp)

        code, resp = self.cmd(b'DATA')
        assert code==b'354', 'data refused, %s, %s' % (code, resp)
        return code, resp

    def body(self, content=''):
        """ Send message body to the smtp server.  You can include the Subject:
        line in this if you want.  This is likely your last transaction before QUIT """
        self.debug_message("Sending message body")
        if content:
            self._sock.send(content.encode("utf-8"))
        self._sock.send(b'\r\n.\r\n') # the five letter sequence marked for ending
        line = self.readline()
        return (int(line[:3].decode()), line[4:].strip().decode())

    def quit(self):
        """ Send QUIT command to smtp server and close socket"""
        self.cmd(b"QUIT")
        self._sock.close()
