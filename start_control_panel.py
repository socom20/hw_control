from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtWidgets import QApplication, QMessageBox, QFileDialog
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtCore import QTimer


import os, sys
import glob
import json
import cv2
import traceback
import random
import time

sys.path.append("../yolo-face-recognition/ws_client_server")
sys.path.append("../CNC_Controller")

import cp_ui
from webcam_capture import GenderDetectorClient
from CNC_controller import CNC_controller

class HW_ContolApp(QtWidgets.QMainWindow, cp_ui.Ui_MainWindow):
    def __init__(self, parent=None, cfg_file='config.json'):
        super(HW_ContolApp, self).__init__(parent)
        self._connect_ui()
        
        self.cfg_file = cfg_file

        # default config:
        self.cfg_d = {
            'cam_server_ip':'34.69.121.169',
            'cam_server_port':7001,
            'cam_index':0,
            'cam_server_password':'yolo_gender',
            'cam_target_fps':5,
            'cam_preview_size':(640, 480),
            'cam_gender_detection_timeframe':5,
            

            'cnc_serial_port':'/dev/ttyUSB0',
            'cnc_baudrate':115200,
            'cnc_move_speed':1000,
            'cnc_paper_size':(210, 297),
            'cnc_coord_transform':'BL',  # None BL or UR


            
            'male_letters_folder':  r'../gpt2_text_generator/gpt_generations/male',
            'female_letters_folder':r'../gpt2_text_generator/gpt_generations/female',
            'hw_file_ext':'pickle',

            'min_detected_frames_to_send_HW': 20,
            }

        if os.path.exists(self.cfg_file):            
            self.load_config()
        else:
            self.save_config()
            

        self.cap = None
        self.gender_detector=None
        self.gender_timer = None
        
        self.detected_gender = None
        self.detected_gender_p = 0.5
        self.detected_frames   = 0

        self.cnc_controller = None
        
        self.automatic_mode = False
        self._update_mode_label()

        self.on_webcam_test = False
        self.cnc_connected  = False

        self.test_cam_timer = None
        return None



    def _connect_ui(self):
        # Connect the UI
        self.setupUi(self)
        self.btn_StartGenderCap.clicked.connect(self.start_capture)
        self.btn_StopGenderCap.clicked.connect(self.stop_capture)

        # CNC btns
        self.btn_ConnectDisconnect.clicked.connect(self.CNC_switch_connection)

        self.btn_TestPaper.clicked.connect(self.CNC_testPaper)
        self.btn_PenUp.clicked.connect(self.CNC_PenUp)
        self.btn_PenDown.clicked.connect(self.CNC_PenUp)
        self.btn_GoHome.clicked.connect(self.CNC_GoHome)
        self.btn_GoTo.clicked.connect(self.CNC_GoTo)

        self.btn_SendRndMale.clicked.connect(self.CNC_send_rnd_Male_file)
        self.btn_SendRndFemale.clicked.connect(self.CNC_send_rnd_Female_file)
        self.btn_SendHWFile.clicked.connect(self.CNC_open_HW_file)

        self.btn_Pause.clicked.connect(self.CNC_pause)
        self.btn_Resume.clicked.connect(self.CNC_resume)
        self.btn_ClearBuffer.clicked.connect(self.CNC_clear_buffer)

        # Cam Test
        self.btn_SwitchMode.clicked.connect(self.switch_mode)
        self.btn_TestWebCam.clicked.connect(self.switch_webcam_test)
        
        return None

    
    def switch_webcam_test(self):
        
        if self.on_webcam_test:
            self.stop_cam_test()
            self.on_webcam_test = not self.on_webcam_test
            self.btn_TestWebCam.setText('Start Test')
        else:
            if self.gender_detector is None:
                self.start_cam_test()
                self.on_webcam_test = not self.on_webcam_test
                self.btn_TestWebCam.setText('Stop Test')
                
            else:
                self._show_exception_msg(Exception('Test is unavailable if GenderCapture is on.'), show_trace=False)

        return None
    

    def _update_mode_label(self):
        self.lbl_mode.setText('Mode = {}'.format('AUTO (@ {} frms)'.format(self.cfg_d['min_detected_frames_to_send_HW']) if self.automatic_mode else 'MANUAL'))
        return None

    def switch_mode(self):
        self.automatic_mode = not self.automatic_mode
        self._update_mode_label()
        
        return None

    
    def _show_exception_msg(self, e=None, show_trace=True):
        buttonReply = QMessageBox.critical(self, 'ERROR:', "{}".format(e), QMessageBox.Ok, QMessageBox.Ok)

        if show_trace:
            traceback.print_exc()
            
        return None

    def _show_file_dialog(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        
        file, _ = QFileDialog.getOpenFileName(self,"Open HW File", "","HW Files (*.{});;All Files (*)".format(self.cfg_d['hw_file_ext']), options=options)
        
        if file == '':
            file = None
        
        return file

    def _CNC_send_HW_file(self, filename=None):
        try:
            if self.cnc_controller is not None:
                self.cnc_controller.send_HW_file(filename)
            else:
                raise Exception('CNC is not connected.')
            
        except Exception as e:
            self._show_exception_msg(e)

        return None
        
    def CNC_open_HW_file(self):
        try:
            filename = self._show_file_dialog()
            if filename is not None:
                self._CNC_send_HW_file(filename)
            
        except Exception as e:
            self._show_exception_msg(e)

        return None

    def _CNC_send_rnd_file(self, search_dir='./'):

        try:
            all_hw_files_v = glob.glob( search_dir )

            if len(all_hw_files_v) == 0:
                raise Exception('No files found at {}'.format(search_dir))
            else:
                filename = random.choice(all_hw_files_v)
                self._CNC_send_HW_file(filename)
        
        except Exception as e:
            self._show_exception_msg(e)

        return None
        

    def CNC_send_rnd_Male_file(self):
        try:
            search_dir = os.path.join(self.cfg_d['male_letters_folder'],
                                      '*.{}'.format(self.cfg_d['hw_file_ext']))

            self._CNC_send_rnd_file(search_dir)
        except Exception as e:
            self._show_exception_msg(e)

        return None


    def CNC_send_rnd_Female_file(self):
        try:
            search_dir = os.path.join(self.cfg_d['female_letters_folder'],
                                      '*.{}'.format(self.cfg_d['hw_file_ext']))

            self._CNC_send_rnd_file(search_dir)
        except Exception as e:
            self._show_exception_msg(e)

        return None
        

    def CNC_disconnect(self):
        try:
            if self.cnc_controller is not None:
                self.cnc_controller.close()
                self.cnc_controller = None
                self.btn_ConnectDisconnect.setText('Connect')
            else:
                raise Exception('CNC is not connected.')
            
        except Exception as e:
            self._show_exception_msg(e)

        return None

    def CNC_connect(self):

        buttonReply = QMessageBox.information(self, 'CNC start position check', 'The initial position of the Pen must be on the Bottom Left corner of the paper.', QMessageBox.Ok, QMessageBox.Ok)

        if self.cnc_controller is not None:
            self.CNC_disconnect()
        try:
            self.cnc_controller = CNC_controller(
                serial_port=self.cfg_d['cnc_serial_port'],
                baudrate=self.cfg_d['cnc_baudrate'],
                move_speed=self.cfg_d['cnc_move_speed'],
                paper_size=self.cfg_d['cnc_paper_size'],
                coord_transform=self.cfg_d['cnc_coord_transform'],
                verbose=False)

            self.cnc_controller.connect()
            self.btn_ConnectDisconnect.setText('Disconnect')
            
        except Exception as e:
            self.cnc_controller = None
            self._show_exception_msg(e)

        return None


    def CNC_switch_connection(self):
        if self.cnc_controller is None:
            self.CNC_connect()            
        else:
            self.CNC_disconnect()
            
        return None

    
    def CNC_testPaper(self):
        try:
            if self.cnc_controller is not None:
                self.cnc_controller.send_test_paper()
            else:
                raise Exception('CNC is not connected.')
        except Exception as e:
            self._show_exception_msg(e)
        
        return None

    def CNC_PenUp(self):
        try:
            if self.cnc_controller is not None:
                self.cnc_controller.send_pen_up()
            else:
                raise Exception('CNC is not connected.')
        except Exception as e:
            self._show_exception_msg(e)
        
        return None

    def CNC_PenDown(self):
        try:
            if self.cnc_controller is not None:
                self.cnc_controller.send_pen_down()
            else:
                raise Exception('CNC is not connected.')
        except Exception as e:
            self._show_exception_msg(e)
        
        return None

    def CNC_GoHome(self):
        try:
            if self.cnc_controller is not None:
                self.cnc_controller.send_go_home()
            else:
                raise Exception('CNC is not connected.')
        except Exception as e:
            self._show_exception_msg(e)
        
        return None


    def CNC_GoTo(self):
        try:
            if self.cnc_controller is not None:
                try:
                    x = float( self.txt_X.text() )
                except:
                    raise ValueError('Unable to parse X coord.')

                try:
                    y = float( self.txt_Y.text() )
                except:
                    raise ValueError('Unable to parse Y coord.')
                
                self.cnc_controller.send_goto(x, y)
            else:
                raise Exception('CNC is not connected.')
        except Exception as e:
            self._show_exception_msg(e)
        
        return None


    def CNC_pause(self):
        try:
            if self.cnc_controller is not None:
                self.cnc_controller.pause()
            else:
                raise Exception('CNC is not connected.')
        except Exception as e:
            self._show_exception_msg(e)
        
        return None


    def CNC_resume(self):
        try:
            if self.cnc_controller is not None:
                self.cnc_controller.resume()
            else:
                raise Exception('CNC is not connected.')
        except Exception as e:
            self._show_exception_msg(e)
        
        return None

    def CNC_clear_buffer(self):
        try:
            if self.cnc_controller is not None:
                self.cnc_controller.clear_buffer()
            else:
                raise Exception('CNC is not connected.')
        except Exception as e:
            self._show_exception_msg(e)

        return None
    
    def load_config(self):
        if self.cfg_file is not None:
            print('- Loading existent config file:', self.cfg_file)
            
            with open(self.cfg_file, 'r') as f:
                cfg_d = json.loads(f.read())

            for k in self.cfg_d.keys():
                if k in cfg_d.keys():
                    if type(cfg_d[k]) == list:
                        cfg_d[k] = tuple(cfg_d[k])
                        
                    if self.cfg_d[k] != cfg_d[k]:
                        print(' - Default config updated: {} = {} >> {}'.format(k, self.cfg_d[k], cfg_d[k]))
                        
                    self.cfg_d[k] = cfg_d[k]
                else:
                    print(' - WARNING: key:"{}" not found in the "config.json" file.'.format(k), file=sys.stderr)

        return None

    def save_config(self):

        if self.cfg_file is not None:
            print('- Seving config file:', self.cfg_file)
            with open(self.cfg_file, 'w') as f:
                f.write(json.dumps(self.cfg_d))
                
        return None

    def capture_cam(self):
        if self.cap is not None:
            ret, frame = self.cap.read()
            self.update_img(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            
        return frame
    
    def start_cam_test(self):
        self.cap = cv2.VideoCapture(self.cfg_d['cam_index'])
        self.test_cam_timer = QTimer()
        self.test_cam_timer.timeout.connect(self.capture_cam)
        self.test_cam_timer.start(int(1000/self.cfg_d['cam_target_fps']))
        
        return None

    def stop_cam_test(self):
        if self.test_cam_timer is not None:
            self.test_cam_timer.stop()
            if self.cap is not None and self.cap.isOpened():
                self.cap.release()
                
        return None
    

    def update_gender_label(self):
        if self.gender_detector is not None:
            gender_info = self.gender_detector.get_gender(self.cfg_d['cam_gender_detection_timeframe'])

            if gender_info is None:
                gender_str = '???'
                self.detected_gender   = None
                self.detected_gender_p = 0.5
                self.detected_frames   = 0
            else:
                gender, prob_v, confidence_m = gender_info
                
                gender_str = '{:6s} (prob: {:0.02f}, frames: {:3d})'.format(gender, max(prob_v), self.detected_frames)
                self.detected_gender = gender
                self.detected_gender_p = max(prob_v)
                self.detected_frames = confidence_m.shape[0]
                
                
            self.gender_label.setText('Gender: {}'.format(gender_str))

            if self.automatic_mode:
                if self.detected_frames > self.cfg_d['min_detected_frames_to_send_HW']:
                    if self.detected_gender == 'male':
                        self.CNC_send_rnd_Male_file()
                    else:
                        self.CNC_send_rnd_Female_file()

                    self.switch_mode()
                
        return None

    
    def start_capture(self):
        
        if self.on_webcam_test:
            self.switch_webcam_test()
            
        
        if self.gender_detector is None:
            print(' Starting Capture ...')
            
            self.cam_label.setGeometry(QtCore.QRect(self.cam_label.x(),
                                                    self.cam_label.y(),
                                                    self.cfg_d['cam_preview_size'][0],
                                                    self.cfg_d['cam_preview_size'][1]))

            
            self.gender_detector = GenderDetectorClient(
                self.cfg_d['cam_index'],
                self.cfg_d['cam_target_fps'],
                self.cfg_d['cam_server_ip'],
                self.cfg_d['cam_server_port'],
                self.cfg_d['cam_server_password'],
                self)

            
            self.gender_timer = QTimer()
            self.gender_timer.timeout.connect(self.update_gender_label)
            self.gender_timer.start(500)

        self.gender_detector.start_recognition()

        return None


    def stop_capture(self):
        print(' Stoping Capture ...')

        if self.gender_detector is not None:
            self.gender_detector.stop_recognition()
            
        return None


    def update_img(self, img=None, win_name=None):
        self.last_detection_time = time.time()
        
        frame = cv2.resize(img, self.cfg_d['cam_preview_size'] )
        
        image = QImage(frame, frame.shape[1], frame.shape[0], 
                       frame.strides[0], QImage.Format_RGB888)

        self.cam_label.setPixmap(QPixmap.fromImage(image))

        return None


    def close_windows(self):
        return None


    def closeEvent(self, event):
        if self.on_webcam_test:
            self.switch_webcam_test()

        if self.cnc_controller is not None:
            self.CNC_disconnect()
            
        if self.gender_detector is not None:
            self.gender_detector.close()

        return None
        
        
    
def main():
    app = QApplication(sys.argv)
    control_win = HW_ContolApp()
    control_win.show()
    app.exec_()

    return control_win




if __name__ == '__main__':
    
    control_win = main()
