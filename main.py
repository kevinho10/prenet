from __future__ import print_function
from PIL import Image
import torch.utils.data as data
import os
import PIL
import argparse
from tqdm import tqdm
import torch.optim as optim
from data_loader import load_data
from torch.optim import lr_scheduler
import torch.backends.cudnn as cudnn
import re
from utils import *
from torchvision import transforms
import model
import numpy
from sklearn.metrics import classification_report

os.environ["CUDA_VISIBLE_DEVICES"] = "0"

def parse_option():
    parser = argparse.ArgumentParser('Progressive Region Enhancement Network(PRENet) for training and testing')

    parser.add_argument('--batchsize', default=2, type=int, help="batch size for single GPU")
    parser.add_argument('--dataset', type=str, default='food101', help='food2k, food101, food500')
    parser.add_argument('--image_path', type=str, default="Documents/food101/images/", help='path to dataset')
    parser.add_argument("--train_path", type=str, default="Documents/food101/meta_data/train_full.txt", help='path to training list')
    parser.add_argument("--test_path", type=str, default="Documents/food101/meta_data/test_full.txt",
                        help='path to testing list')
    parser.add_argument('--weight_path', default="Downloads/food2k_resnet50_0.0001.pth", help='path to the pretrained model')
    parser.add_argument('--use_checkpoint', action='store_true',
                        help="whether to use gradient checkpointing to save memory")
    parser.add_argument('--checkpoint', type=str, default="E:/Pretrained_model/model.pth",
                        help="the path to checkpoint")
    parser.add_argument('--output_dir', default='output', type=str, metavar='PATH',
                        help='root of output folder, the full path is <output>/<model_name>/<tag> (default: output)')
    parser.add_argument("--learning_rate", default=1e-4, type=float,
                        help="The initial learning rate for SGD.")
    parser.add_argument("--epoch", default=200, type=int,
                        help="The number of epochs.")
    parser.add_argument("--test_one", action='store_true',
                        help="Classify an image")
    parser.add_argument("--test_a_dataset", action='store_true',
                        help="Test a dataset of images")
    parser.add_argument("--train", action='store_true',
                        help="Train model.")
    parser.add_argument("--food_img", help="Path to food image to predict.")
    args, unparsed = parser.parse_known_args()
    return args

def train(nb_epoch, trainloader, testloader, batch_size, store_name, start_epoch, net,optimizer,exp_lr_scheduler):
    exp_dir = store_name
    try:
        os.stat(exp_dir)
    except:
        os.makedirs(exp_dir)


    CELoss = nn.CrossEntropyLoss()
    KLLoss = nn.KLDivLoss(reduction="batchmean")


    max_val_acc = 0
    #val_acc, val5_acc, _, _, val_loss = test(net, CELoss, batch_size, testloader)

    for epoch in range(start_epoch, nb_epoch):

        print('\nEpoch: %d' % epoch)
        net.train()
        train_loss = 0
        train_loss1 = 0
        train_loss2 = 0
        train_loss3 = 0
        train_loss4 = 0
        correct = 0
        total = 0
        idx = 0
        batch_idx = 0
        u1 = 1
        u2 = 0.5
        for (inputs, targets) in tqdm(trainloader):
            idx = batch_idx
            if inputs.shape[0] < batch_size:
                continue
            inputs, targets = inputs.cuda(), targets.cuda()
            print(f"target {targets}")
            inputs, targets = Variable(inputs), Variable(targets)
            print(f"tar2 {targets}")

            # Step 1
            optimizer.zero_grad()
            #inputs1 = jigsaw_generator(inputs, 8)
            _, _, _, _, output_1, _, _ = net(inputs, False)
            #print(output_1.shape)
            loss1 = CELoss(output_1, targets) * 1
            loss1.backward()
            optimizer.step()

            # Step 2
            optimizer.zero_grad()
            #inputs2 = jigsaw_generator(inputs, 4)

            _, _, _, _, _, output_2, _, = net(inputs, False)
            #print(output_2.shape)
            loss2 = CELoss(output_2, targets) * 1
            loss2.backward()
            optimizer.step()

            # Step 3
            optimizer.zero_grad()
            #inputs3 = jigsaw_generator(inputs, 2)
            _, _, _, _, _, _, output_3 = net(inputs, False)
                #print(output_3.shape)
            loss3 = CELoss(output_3, targets) * 1
            loss3.backward()
            optimizer.step()


            optimizer.zero_grad()
            x1, x2, x3, output_concat, _, _, _ = net(inputs,True)
            concat_loss = CELoss(output_concat, targets) * 2


            #loss4 = -KLLoss(F.softmax(x1, dim=1), F.softmax(x2, dim=1)) / batch_size
            #loss5 = -KLLoss(F.softmax(x1, dim=1), F.softmax(x3, dim=1)) / batch_size
            loss6 = -KLLoss(F.softmax(x2, dim=1), F.softmax(x1, dim=1))
            #loss7 = -KLLoss(F.softmax(x2, dim=1), F.softmax(x3, dim=1)) / batch_size
            loss8 = -KLLoss(F.softmax(x3, dim=1), F.softmax(x1, dim=1))
            loss9 = -KLLoss(F.softmax(x3, dim=1), F.softmax(x2, dim=1))

            Klloss = loss6 + loss8 + loss9

            totalloss = u1 * concat_loss + u2 * Klloss
            totalloss.backward()
            optimizer.step()

            #  training log
            _, predicted = torch.max(output_concat.data, 1)
            total += targets.size(0)
            correct += predicted.eq(targets.data).cpu().sum()

            train_loss += (loss1.item() + loss2.item() + loss3.item() + concat_loss.item())
            train_loss1 += loss1.item()
            train_loss2 += loss2.item()
            train_loss3 += loss3.item()
            train_loss4 += concat_loss.item()

            if batch_idx % 10 == 0:
                print(
                    'Step: %d | Loss1: %.3f | Loss2: %.5f | Loss3: %.5f | Loss_concat: %.5f | Loss: %.3f | Acc: %.3f%% (%d/%d)' % (
                    batch_idx, train_loss1 / (batch_idx + 1), train_loss2 / (batch_idx + 1),
                    train_loss3 / (batch_idx + 1), train_loss4 / (batch_idx + 1), train_loss / (batch_idx + 1),
                    100. * float(correct) / total, correct, total))
            batch_idx += 1

        exp_lr_scheduler.step()

        train_acc = 100. * float(correct) / total
        train_loss = train_loss / (idx + 1)
        with open(exp_dir + '/results_train.txt', 'a') as file:
            file.write(
                'Iteration %d | train_acc = %.5f | train_loss = %.5f | Loss1: %.3f | Loss2: %.5f | Loss3: %.5f | Loss_concat: %.5f |\n' % (
                epoch, train_acc, train_loss, train_loss1 / (idx + 1), train_loss2 / (idx + 1), train_loss3 / (idx + 1),
                train_loss4 / (idx + 1)))

        val_acc, val5_acc, val_acc_com, val5_acc_com, val_loss = test(net, CELoss, batch_size, testloader,True)
        if val_acc > max_val_acc:
            max_val_acc = val_acc
            torch.save({
                'epoch': epoch,
                'model_state_dict': net.state_dict(),
                'optimizer_state_dict': optimizer.state_dict(),
                'loss': train_loss}, './' + store_name + '/model.pth')
        with open(exp_dir + '/results_test.txt', 'a') as file:
            file.write(
                'Iteration %d, top1 = %.5f, top5 = %.5f, top1_combined = %.5f, top5_combined = %.5f, test_loss = %.6f\n' % (
                    epoch, val_acc, val5_acc, val_acc_com, val5_acc_com, val_loss))

class PMG(nn.Module):
    torch.nn.Module.dump_patches = True

model.PMG = PMG
def main():
    args = parse_option()
    if args.train or args.test_a_dataset:
        train_dataset, train_loader, test_dataset, test_loader = \
            load_data(image_path=args.image_path, train_dir=args.train_path, test_dir=args.test_path,batch_size=args.batchsize)
        print('Data Preparation : Finished')
    if args.dataset == "food101":
        NUM_CATEGORIES = 101
    elif args.dataset == "food500":
        NUM_CATEGORIES = 500
    elif args.dataset == "food2k":
        NUM_CATEGORIES = 2000


    net = load_model('resnet50',pretrain=False,require_grad=True,num_class=NUM_CATEGORIES)
    #net.fc = nn.Linear(2048, 2000)
    state_dict = {}
    pretrained = torch.load(args.weight_path, map_location=torch.device('cpu'))
    
    for k, v in pretrained.module.state_dict().items():
        if k in net.state_dict().keys():
            if 'sconv' in k and 'weight' in k:
                state_dict[k] = v.resize_(1024, 1024, 3, 3)
            else:
                state_dict[k] = v
    
    '''
    for k, v in net.state_dict().items():
        if k[9:] in pretrained.module.state_dict().keys() and "fc" not in k:
            state_dict[k] = pretrained[k[9:]]
        elif "xx" in k and re.sub(r'xx[0-9]\.?',".", k[9:]) in pretrained.module.state_dict().keys():
            state_dict[k] = pretrained[re.sub(r'xx[0-9]\.?',".", k[9:])]
        else:
            state_dict[k] = v
            print(k)
    '''
    net.load_state_dict(state_dict, strict=False)
    net.fc = nn.Linear(2048, NUM_CATEGORIES)

    ignored_params = list(map(id, net.features.parameters()))
    new_params = filter(lambda p: id(p) not in ignored_params, net.parameters())
    optimizer = optim.SGD([
        {'params': net.features.parameters(), 'lr': args.learning_rate*0.1},
        {'params': new_params, 'lr': args.learning_rate}
    ],
        momentum=0.9, weight_decay=5e-4)

    exp_lr_scheduler = lr_scheduler.StepLR(optimizer, step_size=2, gamma=0.9)
    for p in optimizer.param_groups:
        outputs = ''
        for k, v in p.items():
            if k == 'params':
                outputs += (k + ': ' + str(v[0].shape).ljust(30) + ' ')
            else:
                outputs += (k + ': ' + str(v).ljust(10) + ' ')
        print(outputs)

    torch.save(net.state_dict(), 'drive/MyDrive/Colab Notebooks/checkpoints')
    
    if args.train or args.test_a_dataset:
        cudnn.benchmark = True
        net.cuda()
        net = nn.DataParallel(net)

    if args.use_checkpoint:
        net.load_state_dict(torch.load(checkpath))
        model = torch.load(args.checkpoint).module.state_dict()

        net.module.load_state_dict(torch.load(args.checkpoint).module.state_dict())
        print('load the checkpoint')

    if args.test_one:
        #val_acc, val5_acc, val_acc_com, val5_acc_com, val_loss = test(net, nn.CrossEntropyLoss(), args.batchsize, test_loader, True)
        #print('Accuracy of the network on the val images: top1 = %.5f, top5 = %.5f, top1_combined = %.5f, top5_combined = %.5f, test_loss = %.6f\n' % (
        #        val_acc, val5_acc, val_acc_com, val5_acc_com, val_loss))
        img = PIL.Image.open(args.food_img).convert('RGB')
        normalize = transforms.Normalize(mean=[0.5457954, 0.44430383, 0.34424934],
                                     std=[0.23273608, 0.24383051, 0.24237761])
        test_transform = transforms.Compose([
            transforms.Resize((550, 550)),
            transforms.CenterCrop((448, 448)),
            transforms.ToTensor(),
            normalize
        ])
        trans_img = test_transform(img).unsqueeze(0)
        print(f'shape: {trans_img.shape}')
        net.eval()

        with torch.no_grad():

            _, _, _, output_concat, o1, o2, o3 = net(trans_img,True)

        print(f'type: {numpy.argmax(output_concat + o1 + o2 + o3)}')
        return

    if args.test_a_dataset:
        net.eval()
        names = ['Apple pie', 'Baby back ribs', 'Baklava', 'Beef carpaccio', 'Beef tartare', 'Beet salad', 'Beignets', 'Bibimbap', 'Bread pudding', 'Breakfast burrito', 'Bruschetta', 
        'Caesar salad', 'Cannoli', 'Caprese salad', 'Carrot cake', 'Ceviche', 'Cheesecake', 'Cheese plate', 'Chicken curry', 'Chicken quesadilla', 'Chicken wings', 'Chocolate cake', 
        'Chocolate mousse', 'Churros', 'Clam chowder', 'Club sandwich', 'Crab cakes', 'Creme brulee', 'Croque madame', 'Cup cakes', 'Deviled eggs', 'Donuts', 'Dumplings', 'Edamame', 
        'Eggs benedict', 'Escargots', 'Falafel', 'Filet mignon', 'Fish and chips', 'Foie gras', 'French fries', 'French onion soup', 'French toast', 'Fried calamari', 'Fried rice', 
        'Frozen yogurt', 'Garlic bread', 'Gnocchi', 'Greek salad', 'Grilled cheese sandwich', 'Grilled salmon', 'Guacamole', 'Gyoza', 'Hamburger', 'Hot and sour soup', 'Hot dog', 
        'Huevos rancheros', 'Hummus', 'Ice cream', 'Lasagna', 'Lobster bisque', 'Lobster roll sandwich', 'Macaroni and cheese', 'Macarons', 'Miso soup', 'Mussels', 'Nachos', 
        'Omelette', 'Onion rings', 'Oysters', 'Pad thai', 'Paella', 'Pancakes', 'Panna cotta', 'Peking duck', 'Pho', 'Pizza', 'Pork chop', 'Poutine', 'Prime rib', 
        'Pulled pork sandwich', 'Ramen', 'Ravioli', 'Red velvet cake', 'Risotto', 'Samosa', 'Sashimi', 'Scallops', 'Seaweed salad', 'Shrimp and grits', 'Spaghetti bolognese', 
        'Spaghetti carbonara', 'Spring rolls', 'Steak', 'Strawberry shortcake', 'Sushi', 'Tacos', 'Takoyaki', 'Tiramisu', 'Tuna tartare', 'Waffles']

        predicted = []
        real = []

        for (inputs, targets) in tqdm(test_loader):

            inputs, targets = inputs.cuda(), targets.cuda()
            inputs, targets = Variable(inputs), Variable(targets)

            with torch.no_grad():
                _, _, _, output_concat, o1, o2, o3 = net(inputs,True)
                res = output_concat + o1 + o2 + o3
                v, i = torch.max(res,1)
                predicted.append(i.item()) 
                real.append(targets.item())
                
        print(classification_report(real, predicted, target_names=names))

    if args.train:
        train(nb_epoch=args.epoch,             # number of epoch
                trainloader=train_loader,
                testloader=test_loader,
                batch_size=args.batchsize,         # batch size
                store_name='drive/MyDrive/Colab Notebooks/checkpoints',     # folder for output
                start_epoch=0,
                net=net,
                optimizer = optimizer,
                exp_lr_scheduler=exp_lr_scheduler)         # the start epoch number when you resume the training

if __name__ == "__main__":
    main()