import cv2
from datetime import date
from pydantic import validate_call, ValidationError
from enum import Enum


arucoDict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_36h11)
detectParams = cv2.aruco.DetectorParameters()
tagDetector = cv2.aruco.ArucoDetector(arucoDict, detectParams)

class Locale(Enum):
    InTransit = 0
    JurassicPark = 1
    JustInTime = 2

    def toString(self):
        if self.value == 0:
            return "In Transit"
        elif self.value == 1:
            return "At Jurassic Park"
        elif self.value == 2:
            return "At Just In Time"

class Cart:
    @validate_call
    def __init__(self, id: int, name: str, location: Locale, dateWarehouse: date, dateUsage: date, procInfo):
        self.__name = name
        self.__dateWarehouse = dateWarehouse
        self.__dateUsage = dateUsage
        self.__procInfo = procInfo
        self.__location = location
        self.__tagImage = cv2.aruco.generateImageMarker(arucoDict, id, 200)
        self.__id = id

    # Setter Methods
    @validate_call
    def updateWarehouseDate(self, date:date):
        self.__dateWarehouse = date

    @validate_call
    def updateUsageDate(self, date:date):
        self.__dateUsage = date

    def updateProcInfo(self, info):
        self.__procInfo = info
    
    @validate_call
    def updateLocation(self, location:Locale):
        self.__location = location

    # Getter Methods
    def getName(self):
        return self.__name
    
    def getWarehouseDate(self):
        return self.__dateWarehouse
    
    def getUsageDate(self):
        return self.__dateUsage
    
    def getProcInfo(self):
        return self.__procInfo
    
    def getLocation(self):
        return self.__location
    
    def getTagImage(self):
        return self.__tagImage
    
    def getId(self):
        return self.__id
    

  

videoCapture = cv2.VideoCapture(0)

print('Camera Feed Started...\nSearching for April Tag... \nPress SPACE to quit')



# For future, no local database; take id to send to cloud, then take info from cloud to fill class or other implementation method for data
fakeDB = {
    42: Cart(42, 'Condor', Locale.JurassicPark, date.today(), date.today(), None),
    43: Cart(43, 'Raven', Locale.JustInTime, date.today(), date.today(), None),
    44: Cart(44, 'Albatross', Locale.JurassicPark, date.today(), date.today(), None)
}



run = True
lastId = -1
while run:
    success, frame = videoCapture.read()
    if not success:
        print('Error: Could not read camera')
        break
    grayFrame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, rejected = tagDetector.detectMarkers(grayFrame)

    if ids is not None:
        cv2.aruco.drawDetectedMarkers(frame, corners, ids)

        # print id
        for currId in ids:
            if currId[0] != lastId:
                print(f"Detecting cart: {fakeDB[currId[0]].getName()} with ID: {currId[0]} {fakeDB[currId[0]].getLocation().toString()} to be used on {fakeDB[currId[0]].getUsageDate().strftime('%D')}")
                lastId = currId[0]
    
    cv2.imshow("AprilTag ProtoType", frame)

    if cv2.waitKey(1) & 0xFF == ord(' '):
        run = False # Double security (doesn't really do all that much but it is technically 2 layers)
        break


videoCapture.release()
cv2.destroyAllWindows()

