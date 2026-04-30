import time
import json
import TempHumidity as th
import Noise as n
import Light as l
import Camera as c

try:
    while(True):
        # Uses all the sensor methods to retrieve their outputs
        capacity = c.run_camera_debug(5, show_window = False) # Runs this for 5 seconds, False = Doesn't show camera output
        temp = th.readTemp()
        humidity = th.readHumid()
        light = l.readLight()
        noise = n.readNoise()
        
#         print("CAPACITY: ", capacity)
#         print("TEMPERATURE: ", temp)
#         print("HUMIDITY: ", humidity)
#         print("LIGHT: ", light)
#         print("NOISE: ", noise)
#         print()

        # Creates a JSON string from all the sensor outputs
        outputs = json.dumps({'CAPACITY': capacity, 'TEMPERATURE': temp,
                              'HUMIDITY': humidity, 'LIGHT': light, 'NOISE': noise})
                              
        print(outputs, end='', flush=True)


        
        time.sleep(10)
        
        


        
        
    

except KeyboardInterrupt:
    print("Shutting down...")

finally:
    c.picam2.stop()   # ✅ Stop camera ONCE, at program end


    #Somehow, send camera feed over to thingsboard


