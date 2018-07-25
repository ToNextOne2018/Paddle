# Copyright (c) 2018 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from parallel_executor_test_base import TestParallelExecutorBase
import paddle.fluid as fluid
import paddle.fluid.core as core
import numpy as np
import paddle
import paddle.dataset.mnist as mnist
import unittest
import os

MNIST_RECORDIO_FILE = "./mnist_test_pe.recordio"


def simple_fc_net(use_feed):
    if use_feed:
        img = fluid.layers.data(name='image', shape=[784], dtype='float32')
        label = fluid.layers.data(name='label', shape=[1], dtype='int64')
    else:
        reader = fluid.layers.open_files(
            filenames=[MNIST_RECORDIO_FILE],
            shapes=[[-1, 784], [-1, 1]],
            lod_levels=[0, 0],
            dtypes=['float32', 'int64'])
        reader = fluid.layers.io.double_buffer(reader)
        img, label = fluid.layers.read_file(reader)
    hidden = img
    for _ in xrange(4):
        hidden = fluid.layers.fc(
            hidden,
            size=200,
            act='tanh',
            bias_attr=fluid.ParamAttr(
                initializer=fluid.initializer.Constant(value=1.0)))
    prediction = fluid.layers.fc(hidden, size=10, act='softmax')
    loss = fluid.layers.cross_entropy(input=prediction, label=label)
    loss = fluid.layers.mean(loss)
    return loss


def fc_with_batchnorm(use_feed):
    if use_feed:
        img = fluid.layers.data(name='image', shape=[784], dtype='float32')
        label = fluid.layers.data(name='label', shape=[1], dtype='int64')
    else:
        reader = fluid.layers.open_files(
            filenames=[MNIST_RECORDIO_FILE],
            shapes=[[-1, 784], [-1, 1]],
            lod_levels=[0, 0],
            dtypes=['float32', 'int64'])
        reader = fluid.layers.io.double_buffer(reader)
        img, label = fluid.layers.read_file(reader)

    hidden = img
    for _ in xrange(1):
        hidden = fluid.layers.fc(
            hidden,
            size=200,
            act='tanh',
            bias_attr=fluid.ParamAttr(
                initializer=fluid.initializer.Constant(value=1.0)))

        hidden = fluid.layers.batch_norm(input=hidden)

    prediction = fluid.layers.fc(hidden, size=10, act='softmax')
    loss = fluid.layers.cross_entropy(input=prediction, label=label)
    loss = fluid.layers.mean(loss)
    return loss


class TestMNIST(TestParallelExecutorBase):
    @classmethod
    def setUpClass(cls):
        os.environ['CPU_NUM'] = str(4)
        # Convert mnist to recordio file
        with fluid.program_guard(fluid.Program(), fluid.Program()):
            reader = paddle.batch(mnist.train(), batch_size=4)
            feeder = fluid.DataFeeder(
                feed_list=[  # order is image and label
                    fluid.layers.data(
                        name='image', shape=[784]),
                    fluid.layers.data(
                        name='label', shape=[1], dtype='int64'),
                ],
                place=fluid.CPUPlace())
            fluid.recordio_writer.convert_reader_to_recordio_file(
                MNIST_RECORDIO_FILE, reader, feeder)

    def _init_data(self, random=True):
        np.random.seed(5)
        if random:
            img = np.random.random(size=[32, 784]).astype(np.float32)
        else:
            img = np.ones(shape=[32, 784], dtype='float32')
        label = np.ones(shape=[32, 1], dtype='int64')
        return img, label

    def _compare_reduce_and_allreduce(self, model, use_cuda, random_data=True):
        if use_cuda and not core.is_compiled_with_cuda():
            return
        self.check_network_convergence(
            model, use_cuda=use_cuda, use_reduce=True)
        self.check_network_convergence(
            model, use_cuda=use_cuda, allow_op_delay=True, use_reduce=True)

        img, label = self._init_data(random_data)

        all_reduce_first_loss, all_reduce_last_loss = self.check_network_convergence(
            model,
            feed_dict={"image": img,
                       "label": label},
            use_cuda=use_cuda,
            use_reduce=False)
        reduce_first_loss, reduce_last_loss = self.check_network_convergence(
            model,
            feed_dict={"image": img,
                       "label": label},
            use_cuda=use_cuda,
            use_reduce=True)

        for loss in zip(all_reduce_first_loss, reduce_first_loss):
            self.assertAlmostEquals(loss[0], loss[1], delta=1e-6)
        for loss in zip(all_reduce_last_loss, reduce_last_loss):
            self.assertAlmostEquals(loss[0], loss[1], delta=1e-4)

    # simple_fc
    def check_simple_fc_convergence(self, use_cuda, use_reduce=False):
        if use_cuda and not core.is_compiled_with_cuda():
            return
        self.check_network_convergence(simple_fc_net, use_cuda=use_cuda)
        self.check_network_convergence(
            simple_fc_net, use_cuda=use_cuda, allow_op_delay=True)

        img, label = self._init_data()

        self.check_network_convergence(
            simple_fc_net,
            feed_dict={"image": img,
                       "label": label},
            use_cuda=use_cuda,
            use_reduce=use_reduce)

    def check_simple_fc_parallel_accuracy(self, use_cuda):
        if use_cuda and not core.is_compiled_with_cuda():
            return

        img, label = self._init_data(random=False)

        single_first_loss, single_last_loss = self.check_network_convergence(
            method=simple_fc_net,
            seed=1000,
            feed_dict={"image": img,
                       "label": label},
            use_cuda=use_cuda,
            use_parallel_executor=False)
        parallel_first_loss, parallel_last_loss = self.check_network_convergence(
            method=simple_fc_net,
            seed=1000,
            feed_dict={"image": img,
                       "label": label},
            use_cuda=use_cuda,
            use_parallel_executor=True)

        for p_f in parallel_first_loss:
            self.assertAlmostEquals(p_f, single_first_loss[0], delta=1e-6)
        for p_l in parallel_last_loss:
            self.assertAlmostEquals(p_l, single_last_loss[0], delta=1e-6)

    def check_batchnorm_fc_convergence(self, use_cuda):
        if use_cuda and not core.is_compiled_with_cuda():
            return

        self.check_network_convergence(fc_with_batchnorm, use_cuda=use_cuda)

        img, label = self._init_data()

        self.check_network_convergence(
            fc_with_batchnorm,
            feed_dict={"image": img,
                       "label": label},
            use_cuda=use_cuda)

    def check_batchnorm_fc_convergence_use_reduce(self, use_cuda):
        if use_cuda and not core.is_compiled_with_cuda():
            return
        self.check_network_convergence(
            fc_with_batchnorm, use_cuda=use_cuda, use_reduce=False)
        """
        img, label = self._init_data()

        all_reduce_first_loss, all_reduce_last_loss = self.check_network_convergence(
            fc_with_batchnorm,
            feed_dict={"image": img,
                       "label": label},
            use_cuda=use_cuda,
            use_reduce=False)
        reduce_first_loss, reduce_last_loss = self.check_network_convergence(
            fc_with_batchnorm,
            feed_dict={"image": img,
                       "label": label},
            use_cuda=use_cuda,
            use_reduce=True)
        """

    def test_batchnorm_fc_with_new_strategy(self):
        self.check_batchnorm_fc_convergence_use_reduce(True)
        # self.check_batchnorm_fc_convergence_use_reduce(False)


if __name__ == '__main__':
    unittest.main()
