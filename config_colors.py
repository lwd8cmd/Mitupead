import cv2
import numpy as np
import cPickle as pickle
import _cam_settings

def nothing(x):
	pass

cap = cv2.VideoCapture(0)
cv2.namedWindow('image')
cv2.namedWindow('tava')
cv2.namedWindow('mask')
cv2.moveWindow('mask', 400, 0)
#eelnev vaartus
minse = [[],[],[]]
maxse = [[],[],[]]
p = 0
try:
	mins, maxs= pickle.load(open("colors.p", "rb"))
except:
	mins = np.array([[255,255,255],[255,255,255],[255,255,255]])
	maxs = np.array([[0,0,0],[0,0,0],[0,0,0]])


cv2.createTrackbar('brush_size','image',1,10, nothing)
cv2.createTrackbar('vahe','image',0,50, nothing)


# mouse callback function
def choose_color(event,x,y,flags,param):
	global mins, maxs, minse, maxse, p, brush_size, vahe

	if event == cv2.EVENT_LBUTTONDOWN:
		nx = brush_size
		ny = brush_size
		pixs=blurred[y-ny:y+ny,x-nx:x+nx,:] 
		minse[p].append(mins[p].copy())
		maxse[p].append(maxs[p].copy())
		mins[p]=np.minimum(mins[p], pixs.min(0).min(0).astype('int16') - vahe).clip(0, 255).astype('uint8')
		maxs[p]=np.maximum(maxs[p], pixs.max(0).max(0).astype('int16') + vahe).clip(0, 255).astype('uint8')

#kustutab viimased maxid minid
def eelmised_varvid():
	global maxs, maxse, mins, minse, p
	try:
		maxs[p] = maxse[p].pop()
		mins[p] = minse[p].pop()
	except:
		mins[p] = np.array([255,255,255])
		maxs[p] = np.array([0,0,0])

cv2.namedWindow('tava')
cv2.setMouseCallback('tava', choose_color)

print("V2ljumiseks vajutada t2hte 'q', v22rtuste salvestamiseks 's', palli seadestamiseks 'p', kollase jaoks 'y' ja sinise jaoks 'b', default on pall")

while(True):
    # Capture frame-by-frame
	_, yuv = cap.read()
	
	#hsv = cv2.cvtColor(frame,cv2.COLOR_BGR2HSV) 
	brush_size =cv2.getTrackbarPos('brush_size','image')
	vahe = cv2.getTrackbarPos('brush_size','image')

    # Display the resulting frame
	blurred = cv2.GaussianBlur(yuv,(3,3),0)
	mask = cv2.inRange(blurred, mins[p], maxs[p])


	cv2.imshow('tava', blurred)
	cv2.imshow('mask', mask)
	k = cv2.waitKey(1) & 0xFF

	if k == ord('q'):
		break
	elif k == ord('p'):
		print('balls')
		p = 0
	elif k == ord('y'):
		print('yellow gate')
		p = 1
	elif k == ord('b'):
		print('blue gate')
		p = 2
	elif k == ord('s'):
		pickle.dump([mins,maxs], open("colors.p", "wb"))
		print('saved')
	elif k == ord('e'):
			eelmised_varvid()
# When everything done, release the capture
cap.release()
cv2.destroyAllWindows()