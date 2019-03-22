import torch
import torch.nn as nn
import numpy as np

from model import *
from utils import *

## TODOS:
## 1. Dump SH in file
## 2. Save models
## 
## Notes:
## 1. SH is not normalized
## 2. Face is normalized and denormalized - shall we not normalize in the first place?

def predict_sfsnet(conv_model, normal_residual_model, albedo_residual_model,
                    light_estimator_model, normal_gen_model, albedo_gen_model,
                    shading_model, image_recon_modelmodel, dl, train_epoch_num = 0,
                    use_cuda = False, out_folder = None):
    # debugging flag to dump image
    fix_bix_dump = 5

    normal_loss = nn.L1Loss()
    albedo_loss = nn.L1Loss()
    sh_loss     = nn.MSELoss()
    recon_loss  = nn.L1Loss() 

    lamda_recon  = 0.5
    lamda_albedo = 0.5
    lamda_normal = 0.5
    lamda_sh     = 0.1

    if use_cuda:
        normal_loss = normal_loss.cuda()
        albedo_loss = albedo_loss.cuda()
        sh_loss     = sh_loss.cuda()
        recon_loss  = recon_loss.cuda()

    for bix, data in enumerate(train_dl):
        albedo, normal, mask, sh, face = data
        if use_cuda:
            albedo = albedo.cuda()
            normal = normal.cuda()
            mask   = mask.cuda()
            sh     = sh.cuda()
            face   = face.cuda()
        
        # Apply Mask on input image
        face = applyMask(face, mask)
        # predicted_face == reconstruction
        predicted_normal, predicted_albedo, predicted_sh, predicted_shading, predicted_face = sfsnet_pipeline(conv_model, normal_residual_model, albedo_residual_model,
                                                                        light_estimator_model, normal_gen_model, albedo_gen_model,
                                                                        shading_model, image_recon_model)
        if bix == fix_bix_dump:
            # save predictions in log folder
            file_name = out_folder + 'val_' + str(train_epoch_num) + '_' + str(fix_bix_dump)
            save_image(predicted_normal, path=file_name + '_normal.png', mask=mask) 
            save_image(predicted_albedo, path=file_name + '_albedo.png', mask=mask) 
            save_image(predicted_face, denormalize=False, path=file_name + '_face.png', mask=mask)
            save_image(predicted_shading, denormalize=False, path=file_name + '_shading.png', mask = mask)
            # TODO:
            # Dump SH as CSV or TXT file
        
        # Loss computation
        # Normal loss
        current_normal_loss = normal_loss(predicted_normal, normal)
        # Albedo loss
        current_albedo_loss = albedo_loss(predicted_albedo, albedo)
        # SH loss
        current_sh_loss     = sh_loss(predicted_sh, sh)
        # Reconstruction loss
        current_recon_loss  = recon_loss(out_recon, face)

        total_loss = lamda_recon * current_recon_loss + lamda_normal * current_normal_loss \
                        + lamda_albedo * current_albedo_loss + lamda_sh * current_sh_loss

        # Logging for display and debugging purposes
        tloss += total_loss.item()
        nloss += current_normal_loss.item()
        aloss += current_albedo_loss.item()
        shloss += current_sh_loss.item()
        rloss += current_recon_loss.item()
    
    len_dl = len(dl)
    # return average loss over dataset
    return tloss / len_dl, nloss / len_dl, aloss / len_dl, shloss / len_dl, rloss / len_dl


def sfsnet_pipeline(conv_model, normal_residual_model, albedo_residual_model,
                    light_estimator_model, normal_gen_model, albedo_gen_model,
                    shading_model, image_recon_model):
    # Following is training pipeline
    # 1. Pass Image from Conv Model to extract features
    out_features = conv_model(face)

    # 2 a. Pass Conv features through Normal Residual
    out_normal_features = normal_residual_model(out_features)
    # 2 b. Pass Conv features through Albedo Residual
    out_albedo_features = albedo_residual_model(out_features)
    
    # 3 a. Generate Normal
    predicted_normal = normal_gen_model(out_normal_features)
    # 3 b. Generate Albedo
    predicted_albedo = albedo_gen_model(out_albedo_features)
    # 3 c. Estimate lighting
    # First, concat conv, normal and albedo features over channels dimension
    all_features = torch.cat((out_features, out_normal_features, out_albedo_features), dim=1)
    # Predict SH
    predicted_sh = light_estimator_model(all_features)

    # 4. Generate shading
    out_shading = shading_model(denorm(predicted_normal), predicted_sh)

    # 5. Reconstruction of image
    out_recon = image_recon_model(out_shading, denorm(predicted_albedo))
        
    return predicted_normal, predicted_albedo, predicted_sh, out_shading, out_recon


def train(conv_model, normal_residual_model, albedo_residual_model,
          light_estimator_model, normal_gen_model, albedo_gen_model,
          shading_model, image_recon_model, train_dl, val_dl,
          num_epochs = 10, log_path = './metadata/', use_cuda=False):

    model_parameters = list(conv_model.parameters()) + list(normal_residual_model.parameters()) \
                       + list(albedo_residual_model.parameters()) + list(light_estimator_model.parameters()) \
                       + list(normal_gen_model.parameters()) + list(albedo_gen_model) \
                       + list(shading_model.parameters()) + list(image_recon_model.parameters())

    optimizer = torch.optim.Adam(model_parameters, lr = 0.001)
    normal_loss = nn.L1Loss()
    albedo_loss = nn.L1Loss()
    sh_loss     = nn.MSELoss()
    recon_loss  = nn.L1Loss() 

    if use_cuda:
        normal_loss = normal_loss.cuda()
        albedo_loss = albedo_loss.cuda()
        sh_loss     = sh_loss.cuda()
        recon_loss  = recon_loss.cuda()


    lamda_recon  = 0.5
    lamda_albedo = 0.5
    lamda_normal = 0.5
    lamda_sh     = 0.1

    if use_cuda:
        loss = loss.cuda()
        normal_loss = normal_loss.cuda()
        albedo_loss = albedo_loss.cuda()
        sh_loss     = sh_loss.cuda()
        recon_loss  = recon_loss.cuda()

    train_set_len = len(train_dl)
    val_set_len   = len(val_dl)

    for epoch in range(1, num_epochs+1):
        tloss = 0 # Total loss
        nloss = 0 # Normal loss
        aloss = 0 # Albedo loss
        shloss = 0 # SH loss
        rloss = 0 # Reconstruction loss

        for _, data in enumerate(train_dl):
            albedo, normal, mask, sh, face = data
            if use_cuda:
                albedo = albedo.cuda()
                normal = normal.cuda()
                mask   = mask.cuda()
                sh     = sh.cuda()
                face   = face.cuda()
            
            # Apply Mask on input image
            face = applyMask(face, mask)

            predicted_normal, predicted_albedo, predicted_sh, out_shading out_recon = sfsnet_pipeline(conv_model, normal_residual_model, albedo_residual_model, \
                                                                                        light_estimator_model, normal_gen_model, albedo_gen_model, \
                                                                                        shading_model, image_recon_model)            

            # Loss computation
            # Normal loss
            current_normal_loss = normal_loss(predicted_normal, normal)
            # Albedo loss
            current_albedo_loss = albedo_loss(predicted_albedo, albedo)
            # SH loss
            current_sh_loss     = sh_loss(predicted_sh, sh)
            # Reconstruction loss
            # Edge case: Shading generation requires denormalized normal and sh
            # Hence, denormalizing face here
            current_recon_loss  = recon_loss(out_recon, denorm(face))

            total_loss = lamda_recon * current_recon_loss + lamda_normal * current_normal_loss \
                            + lamda_albedo * current_albedo_loss + lamda_sh * current_sh_loss

            optimizer.zero_grad()
            total_loss.backward()
            optimizer.step()

            # Logging for display and debugging purposes
            tloss += total_loss.item()
            nloss += current_normal_loss.item()
            aloss += current_albedo_loss.item()
            shloss += current_sh_loss.item()
            rloss += current_recon_loss.item()

        
        print('Epoch: {} - Total Loss: {}, Normal Loss: {}, Albedo Loss: {}, SH Loss: {}, Recon Loss: {}'.format(epoch, tloss, \
                    nloss, aloss, shloss, rloss))
        if epoch % 1 == 0:
            print('Training set results: Total Loss: {}, Normal Loss: {}, Albedo Loss: {}, SH Loss: {}, Recon Loss: {}'.format(tloss / train_set_len, \
                    nloss / train_set_len, aloss / train_set_len, shloss / train_set_len, rloss / train_set_len))
            v_total, v_normal, v_albedo, v_sh, v_recon = predict(conv_model, normal_residual_model, albedo_residual_model,
                                                                light_estimator_model, normal_gen_model, albedo_gen_model,
                                                                shading_model, image_recon_model, val_dl)

            print('Train Accuracy: {}, Val Accuracy: {}'.format(predict(model, train_dl), predict(model, val_dl, write_to_file='Val_data.csv')))
            # TODO: MODEL SAVING
            # torch.save(model.cpu().state_dict(), log_path + 'model_'+str(epoch)+'.pkl')