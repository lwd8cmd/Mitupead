# Mitupead Robotix project 2014
# Lauri Hamarik & Joosep Kivastik
# Camera module

import numpy as np
import cv2
import threading
import cPickle as pickle
import subprocess
import time
import segment
from collections import deque

try:
	import _cam_settings
except:
	print('cam: settings not set')

class Cam(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)
		self.run_it	= True
		self.gate	= 0#0==yellow,1==blue
		self.gates	= [None, None]
		self.gates_last = [[999, 0], [999, 0]]
		self.frame_balls	= []#balls[]=[x,y,w,h,area]
		self.largest_ball	= None
		self.fps	= 60
		with open('colors/colors.pkl', 'rb') as fh:#color lookup table
			self.colors_lookup = pickle.load(fh)
			segment.set_table(self.colors_lookup)#load table to C module
		self.CAM_D_ANGLE	= 60 * np.pi / 180 / 640
		with open('distances.pkl', 'rb') as fh:#fitted distance parameters
			self.CAM_HEIGHT, self.CAM_DISTANCE, self.CAM_ANGLE, self.Y_FAR, self.X_a, self.X_b, self.W_a, self.W_b = pickle.load(fh)
		self.H_BALL	= 2.15#half height
		self.H_GATE	= 10#half height
		self.fragmented	= np.zeros((480,640), dtype=np.uint8)
		self.t_ball = np.zeros((480,640), dtype=np.uint8)
		self.t_gatey = np.zeros((480,640), dtype=np.uint8)
		self.t_gateb	= np.zeros((480,640), dtype=np.uint8)
		self.t_debug	= np.zeros((480,640,3), dtype=np.uint8)
		self.debugi	= 0
		self.ball_history	= deque([], maxlen=60)
		self.gate	= 0
		self.t_debug_locked	= False
		self.angle_fix	= 0
		ys, xs = np.mgrid[:480,:640]
		self.ball_way = np.abs(xs - self.X_b - ys * self.X_a) < self.W_b + 4 + ys * self.W_a
		self.yarr	= np.arange(480)
		self.xmid	= np.round(self.yarr * self.X_a + self.X_b).astype('uint16')
		
	def open(self):
		self.cam = cv2.VideoCapture(0)
		if self.cam.isOpened():#cam opened
			return True
		self.cam.release()
		print('cam: reset USB')
		for usb in subprocess.check_output(['lsusb']).split('\n')[:-1]:#find cam USB bus/device
			if usb[23:32] == '1415:2000':
				comm	= 'sudo /home/mitupead/Desktop/robotex/usbreset /dev/bus/usb/'+usb[4:7]+'/'+usb[15:18]
				print(subprocess.check_output(comm, shell=True))#reset
		time.sleep(3)
		self.cam = cv2.VideoCapture(0)#restart
		return self.cam.isOpened()
			
	def close(self):
		try:
			self.cam.release()
		except:
			print('cam: close err')
		
	def calc_location(self, x, y, h, corred):
		d	= (self.CAM_HEIGHT - h) * np.tan(self.CAM_ANGLE - self.CAM_D_ANGLE * y) - self.CAM_DISTANCE#horizontal distance
		tmpa	= 340#far center
		x0	= (self.X_b - y * self.X_a) if corred else (tmpa + (300-tmpa)/480.0 * y)#center line
		alpha	= self.CAM_D_ANGLE * (x - x0)+self.angle_fix
		r	= d / np.cos(alpha)
		return (r, alpha)
			
	def analyze_balls(self, t_ball):
		contours, hierarchy = cv2.findContours(t_ball, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
		self.largest_ball	= None
		s_max	= 0
		self.frame_balls	= []
		#self.t_debug	= np.zeros((480,640), dtype=np.uint8)
		for contour in contours:
			s	= cv2.contourArea(contour)
			if s < 4:#too small
				#print('small', s)
				continue
			x, y, w, h = cv2.boundingRect(contour)
			if s < 10 and y > self.Y_FAR:#too small, not far enough
				#print('small2', s, y)
				continue
			ratio	= float(w) / h
			if y + h > 477 and s > 25:#ball's bottom outside the camera view
				s += 10000
				ratio	= 1
			if ratio < 0.5 or ratio > 2.0:
				#print('ratio', ratio)
				continue
			#draw thick line to ball
			ys	= np.repeat(np.arange(y + h, 480), 5)
			xs	= np.linspace(x + w / 2, self.X_b + 480 * self.X_a, num=len(ys)/5).astype('uint16')
			xs	= np.repeat(xs, 5)
			xs[::5] -= 2
			xs[1::5] -= 1
			xs[3::5] += 1
			xs[4::5] += 2
			pxs	= self.fragmented[ys, xs]
			black_pixs	= sum([((pxs[:-i]==6)*(pxs[i:]==5)).sum() for i in [15,16,17,18,19,22,25,28,31]])
			if black_pixs > 10:#white-ball sequence
				#print('black', black_pixs)
				continue
			if s > 10000:#ball close, distance according to top pixel
				coords	= self.calc_location(x + w / 2, y, 2*self.H_BALL, False)
			else:#ball far, distance according to center pixel
				coords	= self.calc_location(x + w / 2, y + h / 2, self.H_BALL, False)
			if coords[0] > 300:#too far, noise
				#print('far', coords[0])
				continue
			self.frame_balls.append(coords)
			if s > s_max:
				s_max	= s
				self.largest_ball	= [coords[0], coords[1], x, y, w, h, s]
					
	def analyze_gate(self, t_gate, gate_nr):
		contours, hierarchy = cv2.findContours(t_gate, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
		self.gates[gate_nr]	= None
		s_max	= 0
		self.debugi += 1
		for contour in contours:
			s	= cv2.contourArea(contour)
			if s < 500:#too small area
				continue
			x, y, w, h = cv2.boundingRect(contour)
			if (h < 18 and y > 2) or (h < 6 and w < 20):#incorrect width, height
				continue
			r, alpha	= self.calc_location(x + w / 2, y + h / 2, self.H_GATE, True)
			if s > s_max:
				s_max	= s
				self.gates[gate_nr]	= [r, alpha, w, h, x, y, s]
				self.gates_last[gate_nr]	= [r, alpha]
		
	def analyze_frame(self):
		#try:
			_, img = self.cam.read()#get frame
			segment.segment(img, self.fragmented, self.t_ball, self.t_gatey, self.t_gateb)#update threshold maps
			self.analyze_balls(self.t_ball)
			self.analyze_gate((self.t_gatey if self.gate == 0 else self.t_gateb), self.gate)#my gate
			if self.gates[self.gate] is None:#other gate
				self.analyze_gate((self.t_gateb if self.gate == 0 else self.t_gatey), 1 - self.gate)
		#except:
		#	print('cam: except')
		
	def cam_warm(self):
		_, img = self.cam.read()#fetch frame w/o image processing

	def UI_screen(self):
		self.t_debug_locked	= True
		self.t_debug	= np.zeros((480,640,3), dtype=np.uint8)
		self.t_debug[self.t_ball > 0] = [0, 0, 255]#balls are shown as red
		self.t_debug[self.t_gatey > 0] = [0, 255, 255]#yellow gate is yellow
		self.t_debug[self.fragmented == 4] = [0, 255, 0]#green
		self.t_debug[self.fragmented == 5] = [255, 255, 255]#white
		self.t_debug[self.fragmented == 6] = [255, 255, 0]#dark
		self.t_debug[self.t_gateb > 0] = [255, 0, 0]#blue gate
		tmp_f	= self.largest_ball
		if tmp_f is not None:
			self.t_debug[tmp_f[3] + tmp_f[5] // 2,:] = [0, 0, 255]#locked ball horizontal
			self.t_debug[:,tmp_f[2] + tmp_f[4] // 2] = [0, 0, 255]#locked ball vertical
		self.t_debug[self.yarr, self.xmid]	= [255, 0, 255]
		#self.t_debug[self.ball_way]	= [255,255,255]
		gate	= self.gates[0]
		if False and gate is not None:#draw gate bounding box
			self.t_debug[gate[5],gate[4]:gate[4]+gate[2]] = [255, 0, 255]
			self.t_debug[gate[5]+gate[3],gate[4]:gate[4]+gate[2]] = [255, 0, 255]
			self.t_debug[gate[5]:gate[5]+gate[3],gate[4]] = [255, 0, 255]
			self.t_debug[gate[5]:gate[5]+gate[3],gate[4]+gate[2]] = [255, 0, 255]
		self.t_debug_locked	= False
