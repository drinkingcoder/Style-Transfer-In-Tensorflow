import tensorflow as tf
import os.path as osp
import os
import losses
import model
from dataset import Dataset
from vgg import Vgg
from util import preprocess, load_config
import numpy as np
import argparse
import matplotlib.pyplot as plt


def solve(Config):
        # get the style feature
        style_features = losses.get_style_feature(Config)
        # prepare some dirs for use
        model_dir = Config.model_dir
        if not osp.exists(model_dir):
            os.mkdir(model_dir)

        # construct the graph and model
        with tf.Graph().as_default():
            # prepare the dataset
            images = Dataset(Config).imagedata_pipelines()
            # the trainnet
            generated = model.inference_trainnet(images)
            # concat the content image and the generated together to save time and feed to the vgg net one time
            # preprocess the generated
            preprocess_generated = preprocess(generated, Config)
            layer_infos = Vgg(Config.feature_path).build(tf.concat([preprocess_generated, images], 0))
            # get the loss
            content_loss = losses.content_loss(layer_infos, Config.content_layers)
            style_loss = losses.style_loss(layer_infos, Config.style_layers, style_features)
            tv_loss = losses.tv_loss(generated)
            loss = Config.style_weight * style_loss + Config.content_weight * content_loss + Config.tv_weight * tv_loss
            tf.add_to_collection('losses', loss)
            total_loss = tf.add_n(tf.get_collection('losses'), name='total_loss')
            # train op
            global_step = tf.Variable(0, name='global_step', trainable=False)
            train_op = tf.train.AdamOptimizer(Config.lr).minimize(total_loss, global_step=global_step)

            # add summary
            with tf.name_scope('losses'):
                tf.summary.scalar('content_loss', content_loss)
                tf.summary.scalar('style_loss', style_loss)
                tf.summary.scalar('tv_loss', tv_loss)
            with tf.name_scope('weighted_losses'):
                tf.summary.scalar('weighted_content_loss', content_loss * Config.content_weight)
                tf.summary.scalar('weighted_style_loss', style_loss * Config.style_weight)
                tf.summary.scalar('weighted_tv_loss', tv_loss * Config.tv_weight)
                tf.summary.scalar('total_loss', total_loss)
            tf.summary.image('generated', generated)
            tf.summary.image('original', images)
            summary = tf.summary.merge_all()
            summary_path = osp.join(model_dir, 'summary')
            if not osp.exists(summary_path):
                os.mkdir(summary_path)
            writer = tf.summary.FileWriter(summary_path)

            # the saver loader
            saver = tf.train.Saver(tf.all_variables())
            restore = tf.train.latest_checkpoint(model_dir)


            # begin training work
            with tf.Session() as sess:
                 # restore the variables
                sess.run([tf.global_variables_initializer(), tf.local_variables_initializer()])
                for var in tf.trainable_variables():
                    print var
                # if we need finetune?
                if Config.finetune:
                    if restore:
                        print 'restoring model from {}'.format(restore)
                        saver.restore(sess, restore)
                    else:
                        print 'no model exist, from scratch'

                # pop the data queue
                coord = tf.train.Coordinator()
                threads = tf.train.start_queue_runners(sess=sess, coord=coord)
                for step in xrange(Config.max_iter):
                    _, loss_value, style_loss_value, content_loss_value, gen = sess.run([train_op, loss,
                                                                            Config.style_weight * style_loss,
                                                                            Config.content_weight * content_loss,
                                                                            images])
                    plt.imshow(np.uint8(gen[0,...]))
                    if step % Config.display == 0:
                        print "{}[iterations], content_loss {}, style_loss {}, train loss {}".format(step,
                                                                                                 content_loss_value,
                                                                                                 style_loss_value,
                                                                                                 loss_value)
                    assert not np.isnan(loss_value), 'model with loss nan'
                    if step % Config.snapshot == 0:
                        # save the generated to see
                        print 'adding summary and saving snapshot...'
                        saver.save(sess, osp.join(model_dir, 'model.ckpt'), global_step=step)
                        summary_str = sess.run(summary)
                        writer.add_summary(summary_str, global_step=step)
                        writer.flush()

                coord.request_stop()
                coord.join(threads)
                sess.close()

                print 'done'


def main(args):
    print 'begin training'
    paser = argparse.ArgumentParser()
    paser.add_argument('-c', '--conf', help='path to the config file')
    args = paser.parse_args()
    Config = load_config(args.conf)
    solve(Config)


if __name__ == '__main__':
    tf.app.run()