import museval
import musdb
import SourceX
import torch
import numpy
import random
from tqdm import tqdm
import sys
import gc

if __name__ == '__main__':
    mus = musdb.DB(subsets="train", split='valid')
    for song in tqdm(range(len(mus)), colour='#e0b0ff', file=sys.stdout):
        with ((torch.no_grad())):
            dtype = torch.float32
            device = torch.device("cuda")
            #print(torch.cuda.is_available())
            torch.set_default_device("cuda")
            model = SourceX.AudioModel(torch.nn.Tanh(), torch.nn.Mish(), torch.nn.ReLU())
            model.to(device='cuda')
            try:
                checkpoint = torch.load(f'istorie antrenari/azi/model.model', weights_only=True)
                model.load_state_dict(checkpoint['model_state_dict'])

                model.eval()
                tqdm.write('am incarcat model.model')
            except:
                tqdm.write('nu am incarcat nici-un state dict')

            rate = 44100
            input_file = mus[song].audio
            stems = mus[song].stems[(1, 2, 4, 3), :, :]


            # genereaza batches
            # posibil memory leak
            x_batches = []
            total_batched = 0
            batch_size = 1323000  # 3 - 30 secunde
            while total_batched < input_file.shape[0]:
                if input_file.shape[0] - batch_size >= total_batched:
                    x_batches.append(input_file[total_batched: total_batched + batch_size, :])
                    total_batched += batch_size
                else:
                    x_batches.append(input_file[total_batched:, :])
                    break

            y_pred = None
            for x_batch in x_batches:
                tqdm.write('started batch')
                x_true = torch.from_numpy(SourceX.genereaza_tensor_din_stereo(x_batch))
                x_true = x_true.to(torch.float32)
                x_true = x_true.to(device="cuda")
                output = model(x_true)

                #s a intamplat ceva funky si acum sunt speriat
                del x_true
                output = output.to(device='cpu')
                if y_pred == None:
                    y_pred = output
                else:
                    y_pred = torch.cat([y_pred, output], dim=1)

                del output

            y_pred_np = y_pred.detach().numpy()

            # in mus[0].stems: 1 = drums, 2 = bass, 3 = other, 4 = vocals
            # in y_true/y_pred: 0 = drums, 1 = bass, 2 = vocals, 3 = other
            estimates = {
                'drums': y_pred_np[0, :, :],
                'bass': y_pred_np[1, :, :],
                'vocals': y_pred_np[2, :, :],
                'other': y_pred_np[3, :, :]
            }
            '''
            try:
                # in mus[0].stems: 1 = drums, 2 = bass, 3 = other, 4 = vocals
                # in y_true/y_pred: 0 = drums, 1 = bass, 2 = vocals, 3 = other
                write(f'istorie antrenari/azi/original.wav', 44100, (mus[song].audio * 32767).astype(np.int16))
                write(f'istorie antrenari/azi/drums.wav', 44100, (stems_original[0, :, :] * 32767).astype(np.int16))
                write(f'istorie antrenari/azi/bass.wav', 44100, (stems_original[1, :, :] * 32767).astype(np.int16))
                write(f'istorie antrenari/azi/vocals.wav', 44100, (stems_original[2, :, :] * 32767).astype(np.int16))
                write(f'istorie antrenari/azi/other.wav', 44100, (stems_original[3, :, :] * 32767).astype(np.int16))
            except:
                tqdm.write("bruh")
            '''
            try:
                scores = museval.eval_mus_track(
                    mus[song],
                    estimates
                )
                tqdm.write(f'{scores}')
            except:
                tqdm.write("problema cu scorurile... womp womp!")

            del y_pred
            del model

            gc.collect()
            torch.cuda.empty_cache()
