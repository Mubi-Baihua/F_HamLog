import socket
import os
import rich

rich.print('[bold blue]Remote Log Server for F HamLog 1.1.0[/bold blue]')
rich.print('[bold yellow]Coded by BI8SQL[/bold yellow]')

listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

def get_free_port():
    port = 8000
    while True:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('0.0.0.0', port))
            return port
        except OSError:
            port += 1

if not os.path.exists('main.fhl'):
    with open('main.fhl', 'w') as f:
        f.write('[]')

absolute_path_fhl = os.path.abspath('main.fhl')
print(f'Log file path:{absolute_path_fhl}')

hn = socket.gethostname()
ip = socket.gethostbyname(hn)
port = get_free_port()
listener.bind(('0.0.0.0',port))

rich.print(f'Listening on:\n[bold magenta]ip:[/bold magenta]{ip}\n[bold magenta]port:[/bold magenta]{port}')

if not os.path.exists('password_xml.txt'):
    with open('password_xml.txt', 'w') as f:
        f.write('000000')

with open('password_xml.txt', 'r') as f:
    password = f.read()

absolute_path_password = os.path.abspath('password_xml.txt')
print(f'Password file path:{absolute_path_password}')
rich.print(f'[bold magenta]Password:[/bold magenta][bold green]{password}[/bold green]')

while True:
    listener.listen(2)
    conn, addr = listener.accept()
    try:

        print(f'Connect - {addr}')
        
        password_DX = conn.recv(1024).decode('utf-8')
        if password_DX == password:
            conn.send('Login'.encode('utf-8'))
            print(f'Login - {addr}')
        else:
            conn.send('Wrong password'.encode('utf-8'))
            conn.close()
        while True:
            DX_d = conn.recv(1024**3)
            DX_data = DX_d.decode('utf-8')
            if DX_data == 'exit':
                print(f'Disconnect - {addr}')
                conn.close()
                break
            elif DX_data == 'send_fhl':
                with open('main.fhl', 'r') as f:
                    conn.send(f.read().encode('utf-8'))
                print(f'Send log file to - {addr}')
            elif '$#$' in DX_data:
                if DX_data.split('$#$')[0] == 'save_fhl':
                    print(f'Save log file from - {addr}')
                    with open('main.fhl', 'w') as f:
                        f.write(DX_data.split('$#$')[1])
            

    except Exception as e:
        print(f'Except_Disconnect - {addr} - {e}')
        conn.close()