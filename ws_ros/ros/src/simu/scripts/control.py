#!/usr/bin/env python3


# Import the necessary libraries
import rospy
from std_msgs.msg import String, Float64, Float64MultiArray, MultiArrayLayout
from sensor_msgs.msg import Image # Image is the message type
from geometry_msgs.msg import Vector3
import time
import numpy as np

import os
import matplotlib.pyplot as plt

class Camera:
    def __init__(self, orient=np.pi/6, resol=[0, 0], hfov=69, vfov=55):
        self.orient = orient
        self.size_img = resol
        self.pos_target = (0, 0)
        self.dist = 0
        self.hfov = hfov
        self.vfov = vfov
        self.thetah = 0
        self.thetav = 0

class Blimp:

    def __init__(self, x0=0, y0=0, z0=0, theta0=0, state0=[0,0,0,0]):
        self.x_target = x0
        self.y_target = y0
        self.z_target = z0
        self.theta = theta0
        self.state = state0 # speedx, speedy, speedz, speedyaw

        self.lis_waypoints = []
        self.camera = Camera()
        self.perfect_dist = 0.5
        self.lis_err = []

        self.forward_command = 0
        self.alt_command = 0
        self.side_top_command = 0
        self.side_bottom_command = 0

        self.Dvx = 0.5
        self.Dvy = 0.5
        self.Dvz = 0.5
        self.Dpsi = 0.5
        self.m = 0.6
        self.Iz = 0.5
        self.L = 0.5

        self.k_f = 1
        self.k_st = 1
        self.k_sb = 1
        self.k_a = 1

        self.A =  np.array([[self.k_f, 0,         0,          0       ], 
                            [0,        self.k_st, -self.k_sb, 0       ],
                            [0,        0,         0,          self.k_a],
                            [0,        self.m * self.L / (2 * self.Iz) * self.k_st, self.m * self.L / (2 * self.Iz) * self.k_sb,  0       ]])

        self.dt = 0.1

    def actualise_speed(self):
        self.state[0] = self.state[0] + (self.forward_command * self.k_f - self.Dvx / self.m * self.state[0] + self.state[3] * self.state[1]) * self.dt
        self.state[1] +=  (self.side_top_command * self.k_st - self.side_bottom_command * self.k_sb - self.Dvy / self.m * self.state[1] - self.state[3] * self.state[0]) * self.dt
        self.state[2] += (self.alt_command * self.k_a - self.Dvz / self.m * self.state[2]) * self.dt
        self.state[3] += (self.m * self.L / (2 * self.Iz) * (self.side_top_command * self.k_st + self.side_bottom_command * self.k_sb) - self.Dpsi / self.Iz * self.state[3]) * self.dt
        self.theta += self.state[3] * self.dt

        cam = self.camera
        cam.thetah = (cam.pos_target[1] - cam.size_img[1] / 2) / 133 * cam.hfov * np.pi / 180
        cam.thetav = (cam.pos_target[0] - cam.size_img[0] / 2) / 100 * cam.vfov * np.pi / 180
        print("thetah = ", cam.thetah * 180 / np.pi)
        self.x_target = cam.dist * np.cos(cam.thetav) * np.cos(cam.thetah)
        self.y_target = -cam.dist * np.cos(cam.thetav) * np.sin(cam.thetah)
        self.z_target = -cam.dist * np.sin(cam.thetav) * np.cos(cam.thetah)
        print("cam.dist = ", cam.dist)

    
    def actualise_err(self):
        alpha = self.camera.orient
        w = [-self.perfect_dist * np.cos(alpha) + 0.3, 0, self.perfect_dist * np.sin(alpha), -self.camera.thetah]
        pos = [-self.x_target * np.cos(alpha) - self.z_target * np.sin(alpha) + 0.3, -self.y_target, -self.z_target * np.cos(alpha) + self.x_target * np.sin(alpha), 0]
        err_square = 0
        for i in range(len(w) - 1):
            err_square += (w[i] - pos[i])**2
        err = np.sqrt(err_square)
        # theta_err = np.abs(self.camera.thetah)
        self.lis_err.append(err)

    def control(self):
        print("pos_target = ", self.camera.pos_target)
        print("size_img = ", self.camera.size_img)
        if self.camera.pos_target != (0, 0) : 
            X = np.array([self.state]).T
            B = np.array([[-self.Dvx / self.m * self.state[0] - self.state[1] * self.state[3]],
                        [-self.Dvy / self.m * self.state[1] + self.state[0] * self.state[3]],
                        [-self.Dvz / self.m * self.state[2]],
                        [-self.Dpsi / self.Iz * self.state[3]]])
            w = np.array([[-self.perfect_dist * np.cos(self.camera.orient) + 0.3, 0, self.perfect_dist * np.sin(self.camera.orient), -self.camera.thetah]]).T
            dw = ddw = np.zeros((4, 1))
            Xint = np.array([[-self.x_target * np.cos(self.camera.orient) + 0.3 - self.z_target * np.sin(self.camera.orient)], 
                             [-self.y_target], 
                             [-self.z_target * np.cos(self.camera.orient) + self.x_target * np.sin(self.camera.orient)], 
                             [0]])
            print("Xobj = ", w.T)
            print("Xint = ", Xint.T)

            V = (w - Xint) + 2 * (dw - X) + ddw
            U = np.linalg.inv(self.A) @ (V - B)
            print("command is ", U.T)

            self.forward_command = U[0, 0]
            self.side_top_command = U[1, 0]
            self.side_bottom_command = U[2, 0]
            self.alt_command = U[3, 0]
        else : 
            self.forward_command = 0
            self.side_top_command = 1
            self.side_bottom_command = 1
            self.alt_command = 0


def callback_dist(msg):
    novabot.camera.dist = msg.data
    

def callback_pos_target(msg):
    novabot.camera.pos_target = msg.data[0:2]
    novabot.camera.size_img = msg.data[2:4]

if __name__ == "__main__":
    t = 0
    lis_t = [t]
    novabot = Blimp()
    rospy.init_node('control')  

    publisher_forward_prop = rospy.Publisher("/forward_prop", Float64, queue_size=20)
    publisher_side_top_prop = rospy.Publisher("/side_top_prop", Float64, queue_size=20)
    publisher_side_bottom_prop = rospy.Publisher("/side_bottom_prop", Float64, queue_size=20)
    publisher_alt_prop = rospy.Publisher("/alt_prop", Float64, queue_size=20)

    subscriber_dist = rospy.Subscriber("/dist_head", Float64, callback_dist)
    subscriber_target = rospy.Subscriber("/pos_target", Float64MultiArray, callback_pos_target)

    r = rospy.Rate(10)

    while not rospy.is_shutdown():

        # actualise blimp
        novabot.actualise_err()
        novabot.actualise_speed()
        novabot.control()

        # publish propeller commands
        forw_msg = Float64()
        forw_msg.data = novabot.forward_command
        publisher_forward_prop.publish(forw_msg)

        side_top_msg = Float64()
        side_top_msg.data = novabot.side_top_command
        publisher_side_top_prop.publish(side_top_msg)

        side_bottom_msg = Float64()
        side_bottom_msg.data = novabot.side_bottom_command
        publisher_side_bottom_prop.publish(side_bottom_msg)

        alt_msg = Float64()
        alt_msg.data = novabot.alt_command
        publisher_alt_prop.publish(alt_msg)

        # save error historic
        plt.plot(lis_t, novabot.lis_err)
        plt.xlabel("time (s)")
        plt.xticks(range(int(t)))
        plt.ylabel("error (m)")
        plt.yticks([i / 2 for i in range(8)])
        plt.title(" error evolution with PID")
        plt.grid(True)
        plt.savefig(os.getcwd() + "/src/simu/figures/error.png")

        
        t += novabot.dt
        lis_t.append(t)
        r.sleep()

