from utils import *
from constant import *
from tensorboard import Tensorboard
import torch
import torch.optim as optim
import torch.nn as nn
from torch.autograd import Variable
from torch.optim.lr_scheduler import ReduceLROnPlateau
import numpy as np
import time
from datetime import datetime
import os
import argparse
import sys
import importlib


def main(args):
    print(args)
    network = importlib.import_module(args.model_def)
    architect = network.architect
    # TODO: maybe get subdir from args, (in checkpoint mode)
    subdir = datetime.strftime(datetime.now(), '%Y%m%d-%H%M%S')
    print('Model name %s' % subdir)
    model_dir = '%s/%s/%s' % (args.models_base_dir, architect, subdir)
    log_dir = '%s/%s/%s' % (args.logs_base_dir, architect, subdir)
    print('Model dir', model_dir)
    print('Log dir', log_dir)
    
    # check and create dir if not existed
    dirs = [model_dir, log_dir]
    for d in dirs:
        if not os.path.isdir(d):
            os.makedirs(d)
    board = Tensorboard(log_dir)
    model = '%s/model.path.tar' % model_dir
    
    # load checkpoint model if exist
    # checkpoint = 
    
    # init training
    # TODO: Try different architecture
    # net = DenseNet121(N_CLASSES).cuda()
    net = network.build()
    parallel_net = torch.nn.DataParallel(net, device_ids=[0]).cuda()
    
    # TODO: Try different optimizer
    optimizer = optim.Adam(net.parameters(), lr=0.001, betas=(0.9, 0.999))
    
    # TODO: Try different loss function
    criterion = nn.BCELoss()
    
    # TODO: Try different scheduler
    scheduler = ReduceLROnPlateau(optimizer, factor=0.1, patience=5, mode='min')
    
    # Get data loader
    train_loader = train_dataloader(image_list_file=args.train_csv, percentage=1)
    # auc need sufficient large amount of either class to make sense, -> always load all here
    valid_loader = test_dataloader(image_list_file=args.val_csv, percentage=1, agumented=args.agumented)
    
    # start training
    batches = min(args.epoch_size, len(train_loader))
    loss_min = float('inf')
    # TODO: Add checkpoint
    for e in range(args.max_nrof_epochs):
        # train
        train(parallel_net, train_loader, optimizer, criterion, e, batches, board)
        
        # validate
        loss_val, aurocs_mean = validate(parallel_net, valid_loader, criterion)
        scheduler.step(loss_val)

        # save best model
        if loss_val < loss_min:
            loss_min = loss_val
            torch.save({
                'epoch': e+1,
                'state_dict': parallel_net.state_dict(),
                'best_loss': loss_min,
                'aurocs_mean': aurocs_mean,
                'optimizer': optimizer.state_dict()
            }, model)
    print('Model name %s' % subdir)
    

def train(model, dataloader, optimizer, criterion, epoch, batches, board):
    model.train()
    iterator = iter(dataloader)
    stime = time.time()
    for i in range(batches):
        #print('Batch')
        data, target = iterator.next()
        data = Variable(torch.FloatTensor(data).cuda())
        target = Variable(torch.FloatTensor(target).cuda())
        
        optimizer.zero_grad()
        output = model(data)
        loss = criterion(output, target)
        loss.backward()
        optimizer.step()
        duration = time.time() - stime
        print('Epochs: [%d][%d/%d]\tTime: %.3f \tLoss: %2.3f' % (epoch, i+1, batches, duration, loss))
        stime += duration
        board.scalar_summary('train_loss', loss.data, epoch * batches + i + 1)
        

def validate(model, dataloader, criterion):
    model.eval()
    losses = []
    targets = torch.FloatTensor().cuda()
    preds = torch.FloatTensor().cuda()
    
    for data, target in dataloader:
        data = Variable(torch.FloatTensor(data).cuda(), volatile=True)
        target = Variable(torch.FloatTensor(target).cuda(), volatile=True)
        pred = model(data)
        loss = criterion(pred, target)
        losses.append(loss.data[0])
        targets = torch.cat((targets, target.data), 0)
        preds = torch.cat((preds, pred.data), 0)
    aurocs = compute_aucs(targets, preds)
    aurocs_mean = np.array(aurocs).mean()
    print('The average AUROC is %.3f' % aurocs_mean)
    return np.mean(losses), aurocs_mean

def parse_arguments(argv):
    parser = argparse.ArgumentParser()
    
    # directory args
    parser.add_argument('--logs_base_dir', type=str, 
        help='Directory where to write event logs.', default=LOG_DIR)
    parser.add_argument('--models_base_dir', type=str,
        help='Directory where to write trained models and checkpoints.', default=MODEL_DIR)
    parser.add_argument('--model_def', type=str,
        help='Directory where to write trained models and checkpoints.', default='models.densenet121')
    
    # train args
    parser.add_argument('--max_nrof_epochs', type=int,
        help='Number of epochs to run.', default=EPOCHS)
    parser.add_argument('--epoch_size', type=int,
        help='Number of batches per epoch.', default=BATCHES)
    parser.add_argument('--batch_size', type=int,
        help='Number of images to process in a batch.', default=BATCHSIZE)
    
    # dataset args
    parser.add_argument('--train_csv', type=str,
        help='List of image to train in csv format', default=CHEXNET_TRAIN_CSV)
    parser.add_argument('--val_csv', type=str,
        help='List of image to validate in csv format', default=CHEXNET_VAL_CSV)
    parser.add_argument('--agumented',
        help='Agumented validate data', action='store_true')
    
    return parser.parse_args(argv)
    
if __name__ == '__main__':
    #TODO: Add argument parser?, or put in config file
    main(parse_arguments(sys.argv[1:]))