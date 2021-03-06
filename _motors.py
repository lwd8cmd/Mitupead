# Mitupead Robotix project 2014
# Lauri Hamarik & Joosep Kivastik
# Motors module

import serial
import numpy as np
import threading
import time
import subprocess

class Motors(threading.Thread):
	def __init__(self):
		threading.Thread.__init__(self)
		self.run_it	= True
		self.DEG120	= 2*np.pi/3
		#motor ids: 1=top left, 2=top right, 3=bottom
		self.motors	= [None, None, None]
		self.coil	= None
		self.sds	= [0, 0, 0]#motor speeds
		self.rsds	= [0, 0, 0]#real motor speeds
		self.buffers	= ['', '', '']
		self.coil_buffer	= ''
		self.stalled	= [False, False, False]
		self.angles	= [-self.DEG120, self.DEG120, 0]
		self.multi	= [1.0, 1.0, 1.0]
		self.is_opened	= False
		self.speed	= 0
		self.direction	= 0
		self.angular_velocity	= 0
		self.coil_enabled	= True#True
		self.has_ball	= False
		self.ball_status	= 0
		self.button = False
		self.opened_status = '?'
		self.tribler_working	= False
		
	def open(self, allow_reset = False):
		try:
			ports = subprocess.check_output('ls /dev/ttyACM*', shell=True).split('\n')[:-1]
		except:
			print('motors: /dev/ttyACM empty')
			return False
		for port in ports:#analyze serial ports
			id_nr	= -1
			try:
				connection_opened = False
				while not connection_opened:
					connection = serial.Serial(port, baudrate=115200, timeout=0.8)
					connection_opened = connection.isOpen()
				i	= 0#try count
				time.sleep(0.5)
				connection.flush()
				while self.run_it:
					try:
						i	+= 1
						if i > 6:#too many tries
							return False
						connection.write('?\n')#ask id
						id_string = connection.readline()#get id
						print('motors: readline ' + port + ', ' + id_string.rstrip())
						if id_string[:4] == '<id:':
							id_nr = int(id_string[4])
							if id_nr == 4 and self.coil_enabled:#found coil
								self.coil	= connection
								print('motors: coil at ' + port)
							else:
								self.motors[id_nr - 1] = connection#found motor
								print('motors: motor ' + str(id_nr) + ' at ' + port)
							if not None in self.motors and (self.coil is not None or not self.coil_enabled):
								self.is_opened = True
								return True
							break
					except:
						continue
			except:
				continue
		if allow_reset:
			self.close()
			self.reset_usb()
			return self.open(False)
		else:
			return False
			
	def reset_usb(self):
		print('motors: reset USB')
		for usb in subprocess.check_output(['lsusb']).split('\n')[:-1]:
			if usb[23:32] == '16c0:047a':
				comm	= 'sudo /home/mitupead/Desktop/robotex/usbreset /dev/bus/usb/'+usb[4:7]+'/'+usb[15:18]
				print(subprocess.check_output(comm, shell=True))
		time.sleep(2)
		
	def motor_write(self, i, comm):
		if self.is_opened:
			try:
				self.motors[i].write(comm + '\n')
			except:
				print('motors: err write ' + comm + ' ' + str(i))
				
	def tribler(self, enable):
		if enable is not self.tribler_working:
			self.coil_write('tg' if enable else 'ts')
			self.tribler_working = enable
			print('motors: tribler ' + ('T' if enable else 'F'))
			
	def coil_write(self, comm):
		if self.coil is not None:
			try:
				self.coil.write(comm + '\n')
			except:
				print('motors: err coil write ' + comm)
		
	def coil_kick(self, val):
		if self.coil is not None:
			print(str(int(val)))
			self.coil_write('k' + str(int(val)))
	
	def close(self):
		for idx, motor in enumerate(self.motors):#close motors
			if motor is not None:
				if motor.isOpen():
					self.motor_write(idx, 'sd0')#stop motor
					try:
						motor.close()
						print('motor ' + str(idx) + ' closed')
					except:
						print('motors: err motors close')
		self.motors	= [None, None, None]
		if self.coil is not None and self.coil.isOpen():#close coil
			self.coil_write('d')#discharge
			self.coil_write('ts')#stop tribler
			try:
				self.coil.close()
				print('coil closed')
			except:
				print('motors: err coil close')
			self.coil	= None
	
	def move(self, speed, direction, omega):
		#print(speed, direction, omega)
		self.speed	= speed
		self.direction	= direction
		self.angular_velocity	= omega
		self.sds	= [int(round(speed*self.multi[i]*np.sin(direction + self.angles[i]) - omega)) for i in range(3)]
		
	def read_buffer(self, i):
		try:
			while self.motors[i].inWaiting() > 0:
				try:
					char	= self.motors[i].read(1)
					if char == '\n':
						#print(self.buffers[i])
						if i == 1 and self.buffers[i][:3] == '<b:':#start button
							self.button = (self.buffers[i][3:4] == '1')
						if i == 0 and self.buffers[i][:3] == '<p:':#ball button
							self.has_ball = (self.buffers[i][3:4] == '0')
						elif self.buffers[i][:7] == '<stall:':#motors stalled
							self.stalled[i]	= (not self.buffers[i][7:8] == '0')
							print('stall', i)
						self.buffers[i]	= ''
					else:
						self.buffers[i] += char
				except:
					print('motors: except ' + str(i))
					continue
		except:
			print('motors: except')
			
	def read_buffer_coil(self):
		try:
			while self.coil is not None and self.coil.inWaiting() > 0:
				try:
					char	= self.coil.read(1)
					if char == '\n':
						#print(self.coil_buffer)
						if self.coil_buffer[:3] == '<b:':
							has_ball	= self.coil_buffer[3:4] == '4'
							self.has_ball	= has_ball
							print('motors: ball ' + str(has_ball))
						self.coil_buffer	= ''
					else:
						self.coil_buffer += char
				except:
					print('motors: err red_buffer_coil b')
					continue
		except:
			print('motors: err red_buffer_coil')
		
	def update(self):
		if not self.is_opened:
			return
		maxs	= max(self.sds)
		if maxs > 185:
			print('motors: too fast', self.sds)
			#return
			for i in range(3):
				self.sds[i]	= int(self.sds[i] * 180.0 / maxs)
		for i in range(3):
			self.motor_write(i, 'sd' + str(self.sds[i]))
		
	def read_buffers(self):
		if not self.is_opened:
			#print('motors: not opened')
			return
		for i in range(3):
			self.read_buffer(i)
		#self.read_buffer_coil()
		
	def run(self):
		if self.open():#open serial connections
			self.opened_status = '+'
			print('motors: opened')
		else:
			self.opened_status = '-'
			print('motors: opening failed')
			self.close()
			return
		if self.coil is not None:#charge coils
			self.coil_write('c')
		while self.run_it:#ping 1 Hz
			self.update()
			if self.coil is not None:
				self.coil_write('p')#automatic discharge prevention
			time.sleep(1)
		print('motors: close thread')
		self.close()
