import cv2
import re
import random
import numpy as np
import os.path
import scipy.misc
import shutil
import zipfile
import time
import tensorflow as tf
from glob import glob
from urllib.request import urlretrieve
from tqdm import tqdm


class DLProgress(tqdm):
    last_block = 0

    def hook(self, block_num=1, block_size=1, total_size=None):
        self.total = total_size
        self.update((block_num - self.last_block) * block_size)
        self.last_block = block_num


def maybe_download_pretrained_vgg(data_dir):
    """
    Download and extract pretrained vgg model if it doesn't exist
    :param data_dir: Directory to download the model to
    """
    vgg_filename = 'vgg.zip'
    vgg_path = os.path.join(data_dir, 'vgg')
    vgg_files = [
        os.path.join(vgg_path, 'variables/variables.data-00000-of-00001'),
        os.path.join(vgg_path, 'variables/variables.index'),
        os.path.join(vgg_path, 'saved_model.pb')]

    missing_vgg_files = [vgg_file for vgg_file in vgg_files if not os.path.exists(vgg_file)]
    if missing_vgg_files:
        # Clean vgg dir
        if os.path.exists(vgg_path):
            shutil.rmtree(vgg_path)
        os.makedirs(vgg_path)

        # Download vgg
        print('Downloading pre-trained vgg model...')
        with DLProgress(unit='B', unit_scale=True, miniters=1) as pbar:
            urlretrieve(
                'https://s3-us-west-1.amazonaws.com/udacity-selfdrivingcar/vgg.zip',
                os.path.join(vgg_path, vgg_filename),
                pbar.hook)

        # Extract vgg
        print('Extracting model...')
        zip_ref = zipfile.ZipFile(os.path.join(vgg_path, vgg_filename), 'r')
        zip_ref.extractall(data_dir)
        zip_ref.close()

        # Remove zip file to save space
        os.remove(os.path.join(vgg_path, vgg_filename))


def gen_batch_function(data_folder, image_shape):
    """
    Generate function to create batches of training data
    :param data_folder: Path to folder that contains all the datasets
    :param image_shape: Tuple - Shape of image
    :return:
    """
    def get_batches_fn(batch_size):
        """
        Create batches of training data
        :param batch_size: Batch Size
        :return: Batches of training data
      """
        image_paths = glob(os.path.join(data_folder, 'image_2', '*.png'))
        image_paths += glob(os.path.join(data_folder, 'image_2', '*.PNG'))
        lp =glob(os.path.join(data_folder, 'gt_image_2', '*.png'))
        print(len(image_paths),len(lp))
        image_paths.sort()
        lp.sort()
        label_paths = {os.path.basename(image_paths[i]):lp[i] for i in range(len(image_paths))}
        random.shuffle(image_paths)
        for batch_i in range(0, len(image_paths), batch_size):
            images = []
            gt_images = []
            for image_file in image_paths[batch_i:batch_i+batch_size]:
                gt_image_file = label_paths[os.path.basename(image_file)]
                image = scipy.misc.imresize(scipy.misc.imread(image_file), image_shape)
                image=cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
                gt_image = scipy.misc.imread(gt_image_file)
                if(len(gt_image.shape) > 2) :
                  gt_image = (gt_image[:,:,0])
                gt_image = scipy.misc.imresize(gt_image, image_shape)
                if 'c' in os.path.basename(image_file):       
                  gt_bg_c = gt_image == 255
                  gt_bg_i = np.invert(gt_bg_c)
                  temp = np.zeros(gt_image.shape)
                  gt_bg_t = temp !=0
                else:
                  gt_bg_t = gt_image == 255
                  gt_bg_i = np.invert(gt_bg_t)
                  temp = np.zeros(gt_image.shape)
                  gt_bg_c = temp !=0             
                gt_bg_i = gt_bg_i.reshape(*gt_bg_i.shape, 1)
                gt_bg_c = gt_bg_c.reshape(*gt_bg_c.shape, 1)
                gt_bg_t = gt_bg_t.reshape(*gt_bg_t.shape, 1)
                gt_image = np.concatenate((gt_bg_c,gt_bg_t,gt_bg_i), axis=2)

                images.append(image)
                gt_images.append(gt_image)

            yield np.array(images), np.array(gt_images)
    return get_batches_fn


def gen_test_output(sess, logits, keep_prob, image_pl, data_folder, image_shape):
    """
    Generate test output using the test images
    :param sess: TF session
    :param logits: TF Tensor for the logits
    :param keep_prob: TF Placeholder for the dropout keep robability
    :param image_pl: TF Placeholder for the image placeholder
    :param data_folder: Path to the folder that contains the datasets
    :param image_shape: Tuple - Shape of image
    :return: Output for for each test image
    """
    tst_images = glob(os.path.join(data_folder, 'image_2', '*.png'))
    tst_images += glob(os.path.join(data_folder, 'image_2', '*.PNG'))
    for image_file in tst_images:
        image = scipy.misc.imresize(scipy.misc.imread(image_file), image_shape)
        image=cv2.cvtColor(image, cv2.COLOR_BGRA2BGR)
        im_softmax = sess.run(
            [tf.nn.softmax(logits)],
            {keep_prob: 1.0, image_pl: [image]})
        

        im_softmax_c = im_softmax[0][:, 0].reshape(image_shape[0], image_shape[1])
        im_softmax_t = im_softmax[0][:, 1].reshape(image_shape[0], image_shape[1])
        segmentation_c = (im_softmax_c > 0.5).reshape(image_shape[0], image_shape[1], 1)
        segmentation_t = (im_softmax_t > 0.5).reshape(image_shape[0], image_shape[1], 1)
        mask_c = np.dot(segmentation_c, np.array([[0, 255, 0, 127]]))
        mask_c = scipy.misc.toimage(mask_c, mode="RGBA")
        mask_t = np.dot(segmentation_t, np.array([[255, 0, 0, 127]]))
        mask_t = scipy.misc.toimage(mask_t, mode="RGBA")
        street_im = scipy.misc.toimage(image)
        street_im.paste(mask_c, box=None, mask=mask_c)
        street_im.paste(mask_t, box=None, mask=mask_t)




        
#         if 'c' in os.path.basename(image_file):
#           im_softmax = im_softmax[0][:, 0].reshape(image_shape[0], image_shape[1])
#           segmentation = (im_softmax > 0.5).reshape(image_shape[0], image_shape[1], 1)
#           mask = np.dot(segmentation, np.array([[0, 255, 0, 127]]))
#           mask = scipy.misc.toimage(mask, mode="RGBA")
#           street_im = scipy.misc.toimage(image)
#           street_im.paste(mask, box=None, mask=mask)
#         else:
#           im_softmax = im_softmax[0][:, 1].reshape(image_shape[0], image_shape[1])
#           segmentation = (im_softmax > 0.5).reshape(image_shape[0], image_shape[1], 1)
#           mask = np.dot(segmentation, np.array([[255, 0, 0, 127]]))
#           mask = scipy.misc.toimage(mask, mode="RGBA")
#           street_im = scipy.misc.toimage(image)
#           street_im.paste(mask, box=None, mask=mask)

        yield os.path.basename(image_file), np.array(street_im)


def save_inference_samples(runs_dir, data_dir, sess, image_shape, logits, keep_prob, input_image):
    # Make folder for current run
    output_dir = os.path.join(runs_dir, str(time.time()))
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    # Run NN on test images and save them to HD
    print('Training Finished. Saving test images to: {}'.format(output_dir))
    image_outputs = gen_test_output(
        sess, logits, keep_prob, input_image, os.path.join(data_dir, 'data_road_1/testing'), image_shape)
    for name, image in image_outputs:
        scipy.misc.imsave(os.path.join(output_dir, name), image)
