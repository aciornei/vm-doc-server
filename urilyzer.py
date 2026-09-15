from django.core.management.base import BaseCommand 
import datetime
import threading
from laboratory.models import PresentationLaboratory, InvestigationDetail
import socket 
import time
from datetime import timedelta
soh = b'\x01'
stx = b'\x02'
etx = b'\x03'
eot = b'\x04'
enq = b'\x05'
ack = b'\x06'
class Command(BaseCommand):
    help = 'Get appointments' 
    bind_ip = "0.0.0.0"
    bind_port = 8010
    instrument_api = "Urilyzer100"
    clients = []
    def start_server(self):
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        print('starting server ... ')
        server.bind((self.bind_ip, self.bind_port))
        server.listen()
        print('server started', self.bind_ip, self.bind_port)
        return server
    
    def handle(self, *args, **options):
        results = {
            "Bil": {
                "neg": "Negativ",
                "1": "1 mg/dl +",
                "2": "2 mg/dl + +",
                "3": "3 mg/dl + +",
                "4": "4 mg/dl + + +",
            },
            "Ubg": {
                "norm": "Normal",
                "2": "2 mg/dl + ",
                "4": "4 mg/dl + +",
                "8": "8 mg/dl + + +",
                "12": "12 mg/dl + + + +",
            },
            "Ket": {
                "neg": "Negativ",
                "norm": "Normal",
                "10": "10 mg/dl (+)",
                "25": "25 mg/dl +",
                "100": "100 mg/dl + +",
                "300": "300 mg/dl + + +",
            },
            "Asc": {
                "neg": "Negativ",
                "20": "20 mg/dl +",
                "40": "40 mg/dl + +",
            },
            
            "Glu": {
                "norm": "Normal",
                "50": "50 mg/dl +",
                "100": "100 mg/dl + + ",
                "250": "250 mg/dl + + +",
                "500": "500 mg/dl + + + +",
                "1000": "1000 mg/dl + + + +",
                
            }, 
            
            "Pro": {
                "neg": "Negativ",
                "30": "30 mg/dl +",
                "100": "100 mg/dl + +",
                "500": "500 mg/dl + + +",

            }, 
            
            "Ery": {
                "neg": "Negativ",
                "5-10": "5-10 Ery/ml +",
                "50": "50 Ery/ml + +",
                "300": "300 Ery/ml + + +", 

            }, 
            
            "Leu": {
                "neg": "Negativ",
                "25": "25 Leu/ml +",
                "75": "75 Leu/ml + +",
                "500": "500 Leu/ml + + +",
            },
            
            "Nit": {
                "neg": "Negativ",
                "pos": "Pozitiv +",
            },
        }
        def handle_client(client_socket):
            barcode = None
            presentation_laboratory = None
            while True:
                print('waiting for data')
                request = client_socket.recv(1024)
                if not request: break
                client_socket.send(ack)
                data = request.decode('utf-8')
                elements = data.split('|')
                if len(elements) < 2: continue
                first_part = elements[0]
                # O|1|23281|^^^^SAMPLE||R||||||X|||20250228104745
                if "O" in first_part:
                    # we get the barcode and grab the presentation laboratory object
                    barcode = elements[2]
                    try: barcode = int(barcode)
                    except:
                        barcode = None # set it to none to skip even the the next rows
                        continue # skip current row
                    presentation_laboratory = PresentationLaboratory.objects.filter(id=barcode).first()
                    
                # R|1|1^^^Bil|neg|mg/dl||||||autologin|20250228104745|20250228104850
                # this is a result. We get the result only if we received earlier a barcode
                if presentation_laboratory and barcode and "R" in first_part:
                    # this is the api code that is mapped in the database
                    code = elements[2].split('^^^')[1]
                    # this is the result
                    result = elements[3]

                    result = results.get(code, {}).get(result, result)

                    # get the detail based on the mapping data
                    detail = InvestigationDetail.objects.filter(
                        api_code=code, 
                        investigation__instrument__api_name=self.instrument_api).first()
                    if not detail: continue
                    # get the result already added
                    res = presentation_laboratory.presentationitemdetailresult_set.filter(investigation_detail=detail).first()
                    if not res:
                        res = presentation_laboratory.presentationitemdetailresult_set.create(investigation_detail=detail)
                    # update the result only if not valid
                    if not res.valid:
                        res.result = result
                    res.save()

                # reached the and and clean the variables
                if "L|1|N" in data:
                    barcode = None
                    presentation_laboratory = None
                 
                print('received', data)
                time.sleep(0.02)

        server = self.start_server()
        if not server: quit()
        try:
            while True:
                client, addr = server.accept()
                print('new connection', addr[0], addr[1])
                self.clients.append(client)

                client_handler = threading.Thread(target=handle_client, args=(client, ))
                client_handler.start()
                time.sleep(0.5)
        except KeyboardInterrupt:
            print('stopping')
            for client in self.clients:
                try:  
                    client.close()
                except Exception as e:
                    print(e)
            server.close() 

             
    
         

        
