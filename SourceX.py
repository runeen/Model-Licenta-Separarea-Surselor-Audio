import torch
import math
import random
import numpy as np
from torchmetrics.audio import SignalDistortionRatio
import os
os.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"

print(np.__version__)
import musdb
import tqdm
import museval
import torchmetrics
from scipy.io.wavfile import write

from scipy.signal import butter, filtfilt
import scipy.io
from torch import newaxis

import incarca_audio

mus = musdb.DB(download=True)


def genereaza_strat_banda(tensor, filter):
    y = filtfilt(filter[0], filter[1], tensor, 0)
    #print(f'Y: {y}')
    return y

def genereaza_tensor_din_stereo(tensor):
    mono = np.average(tensor, 1).reshape(-1, 1)
    #print(f'MONO SHAPE: {mono.shape}')

    output = np.hstack([tensor, mono])
    #print(f'TENSOR: \n{output}\n\tSHAPE: {output.shape}')

    separated = tensor - mono

    output = np.hstack([output, separated])
    #print(f'TENSOR: \n{output}\n\tSHAPE: {output.shape}')

    output_3_axe = output[..., np.newaxis]


    cutoff = 1000
    fs = mus[0].rate

    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(5, normal_cutoff, btype='low', analog=False)

    output_3_axe_nou = genereaza_strat_banda(output, (b, a))[..., newaxis]

    #output_3_axe    = np.concatenate([output_3_axe, genereaza_strat_banda(output, (b, a))[..., newaxis]], axis=2)


    cutoff = np.array([1000, 10000])
    fs = mus[0].rate

    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(5, normal_cutoff, btype='band', analog=False)

    #output_3_axe = np.concatenate([output_3_axe, genereaza_strat_banda(output, (b, a))[..., newaxis]], axis=2)
    output_3_axe_nou = np.concatenate([output_3_axe_nou, genereaza_strat_banda(output, (b, a))[..., newaxis]], axis=2)


    cutoff = 10000
    fs = mus[0].rate

    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(5, normal_cutoff, btype='high', analog=False)

    #output_3_axe = np.concatenate([output_3_axe, genereaza_strat_banda(output, (b, a))[..., newaxis]], axis=2)
    output_3_axe_nou = np.concatenate([output_3_axe_nou, genereaza_strat_banda(output, (b, a))[..., newaxis]], axis=2)

    #return output_3_axe
    return output_3_axe_nou

def apply_high_pass(tensor):
    tensor = tensor.detach().numpy()
    cutoff = 10
    fs = mus[0].rate

    nyq = 0.5 * fs
    normal_cutoff = cutoff / nyq
    b, a = butter(2, normal_cutoff, btype='high', analog=False)
    y = filtfilt(b, a, tensor, 1)
    y = torch.tensor(y.copy(), requires_grad=True, dtype=torch.float32)
    return y


genereaza_tensor_din_stereo(mus[0].audio)

'''
output_file = tensor_3_axe[:, 2, 1]
print(output_file.dtype)
print(f'OUTPUT TENSOR (TEST) \n{output_file}\n\tSHAPE: {output_file.shape}')
output_file = output_file * 32767
output_file = output_file.astype(np.int16)
print(f'OUTPUT TENSOR (TEST) \n{output_file}\n\tSHAPE: {output_file.shape}')

write("output wav.wav", fs, output_file)
'''

nr_samples = mus[0].audio.shape[0]




class AudioModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.encoder1 = torch.nn.Conv2d(3, 10, (20, 5), padding='same')
        self.encoder2 = torch.nn.Conv2d(10, 15, (20, 5), padding='same')
        self.encoder3 = torch.nn.Conv2d(15, 20, (20, 5), padding='same')
        self.encoder4 = torch.nn.Conv2d(20, 60, (20, 5), padding='same')


        self.decoder4 = torch.nn.Conv2d(60, 20, (20, 5), padding='same')
        self.decoder3 = torch.nn.Conv2d(20, 15, (20, 5), padding='same')
        self.decoder2 = torch.nn.Conv2d(15, 10, (20, 5), padding='same')
        self.decoder1 = torch.nn.Conv2d(10, 3, (20, 5), padding='same')


    def forward(self, x : torch.Tensor):
        x = x.permute(2, 0, 1)
        #saved = [x]

        x = self.encoder1(x)
        #saved.append(x)
        x = self.encoder2(x)
        #saved.append(x)
        x = self.encoder3(x)

        x = self.encoder4(x)


        x = self.decoder4(x)
        x = self.decoder3(x)
        x = self.decoder2(x)
        x = self.decoder1(x)

        #x = x.permute()
        return x[:, :, :2]




dtype = torch.float32
device = torch.device("cuda")
print(torch.cuda.is_available())
torch.set_default_device("cuda")

model = AudioModel()

#original L1Loss
criterion = torch.nn.MSELoss(reduction='mean')
criterion.requires_grad_(True)

print(f'shape musdb {mus}')

#original 2e-5
learning_rate = 2e-4
#original era Adam aici
optimizer = torch.optim.SGD(model.parameters(), lr = learning_rate, momentum=0.9)

torch.set_grad_enabled(True)

sdr = SignalDistortionRatio

for t in range(0, 1000):
    for song in range(len(mus)):
        audio_original = mus[song].audio
        x_true = torch.from_numpy(genereaza_tensor_din_stereo(audio_original))
        audio_original = torch.from_numpy(audio_original).to(device= 'cuda', dtype=torch.float32)

        x_true = x_true.to(torch.float32)
        x_true = x_true.to(device = "cuda")
        #print(f'x_true.shape: {x_true.shape}')

        y_true = torch.from_numpy(mus[song].stems[1:, :, :])
        y_true = y_true.to(torch.float32)
        y_true = y_true.to(device = "cuda")
        #print(f'y_true.shape: {y_true.shape}')

        y_pred = model(x_true)
        y_pred = torch.cat((y_pred, (audio_original - torch.sum(y_pred, dim = 0))[newaxis, ...]), dim = 0)
        temp = y_pred.clone()
        temp[2, :, :] = y_pred[3, :, :]
        temp[3, :, :] = y_pred[2, :, :]
        y_pred = temp
        print(f'y_pred shape: {y_pred.shape}')

        #y_pred = apply_high_pass(y_pred)

        #print(f'y_pred.shape: {y_pred.shape}')



        loss = criterion(y_pred, y_true)
        #if t % 10 == 9:
        #plafoneaza pe la 0.05
        print(f't- {t}, song- {song}, mse: {loss.item()}, rmse:{math.sqrt(loss.item())}')


        if song % 100 == 99:
            y_pred = y_pred.to(device="cpu")
            y_pred_np = y_pred.detach().numpy()
            estimates = {
                'drums': y_pred_np[0, :, :],
                'bass': y_pred_np[1, :, :],
                'other': y_pred_np[2, :, :],
                'vocals': y_pred_np[3, :, :]
            }

            scores = museval.eval_mus_track(
                mus[song],
                estimates
            )

            print(scores)

            try:
                write(f'original.wav', 44100, (mus[song].audio * 32767).astype(np.int16))
                write(f'bass.wav', 44100, (y_pred_np[1, :, :] * 32767).astype(np.int16))
                write(f'drums.wav', 44100, (y_pred_np[0, :, :] * 32767).astype(np.int16))
                write(f'other.wav', 44100, (y_pred_np[2, :, :] * 32767).astype(np.int16))
                write(f'vocals.wav', 44100, (y_pred_np[3, :, :] * 32767).astype(np.int16))
            except:
                print("bruh")


        #sdr, sir, sar, perm = fast_bss_eval.bss_eval_sources(y_pred.T, y_true.T)
        #print(f'SDR: {sdr}')

        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
