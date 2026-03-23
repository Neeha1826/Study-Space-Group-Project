import time
import TempHumidity as th
import Noise as n
import Light as l
#import camera as c


while(True):
    th.readTemp()
    th.readHumid()
    l.readLight()
    n.readNoise()
    #c.getCapacity()
    time.sleep(5)

    #Somehow, send camera feed over to thingsboard


