from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import os.path

import tensorflow.python.platform

from tensorflow.python.framework import test_util
from tensorflow.python.platform import gfile
from tensorflow.python.platform import googletest
from tensorflow.python.summary import event_accumulator
from tensorflow.python.summary import event_multiplexer


def _AddEvents(path):
  if not gfile.IsDirectory(path):
    gfile.MakeDirs(path)
  fpath = os.path.join(path, 'hypothetical.tfevents.out')
  with gfile.GFile(fpath, 'w'):
    return fpath


def _CreateCleanDirectory(path):
  if gfile.IsDirectory(path):
    gfile.DeleteRecursively(path)
  gfile.MkDir(path)


class _FakeAccumulator(object):

  def __init__(self, path):
    self._path = path
    self.autoupdate_called = False
    self.autoupdate_interval = None
    self.reload_called = False

  def Tags(self):
    return {event_accumulator.IMAGES: ['im1', 'im2'],
            event_accumulator.HISTOGRAMS: ['hst1', 'hst2'],
            event_accumulator.COMPRESSED_HISTOGRAMS: ['cmphst1', 'cmphst2'],
            event_accumulator.SCALARS: ['sv1', 'sv2']}

  def Scalars(self, tag_name):
    if tag_name not in self.Tags()[event_accumulator.SCALARS]:
      raise KeyError
    return ['%s/%s' % (self._path, tag_name)]

  def Histograms(self, tag_name):
    if tag_name not in self.Tags()[event_accumulator.HISTOGRAMS]:
      raise KeyError
    return ['%s/%s' % (self._path, tag_name)]

  def CompressedHistograms(self, tag_name):
    if tag_name not in self.Tags()[event_accumulator.COMPRESSED_HISTOGRAMS]:
      raise KeyError
    return ['%s/%s' % (self._path, tag_name)]

  def Images(self, tag_name):
    if tag_name not in self.Tags()[event_accumulator.IMAGES]:
      raise KeyError
    return ['%s/%s' % (self._path, tag_name)]

  def AutoUpdate(self, interval):
    self.autoupdate_called = True
    self.autoupdate_interval = interval

  def Reload(self):
    self.reload_called = True


def _GetFakeAccumulator(path, size_guidance):  # pylint: disable=unused-argument
  return _FakeAccumulator(path)


class EventMultiplexerTest(test_util.TensorFlowTestCase):

  def setUp(self):
    super(EventMultiplexerTest, self).setUp()
    event_accumulator.EventAccumulator = _GetFakeAccumulator

  def testEmptyLoader(self):
    x = event_multiplexer.EventMultiplexer()
    self.assertEqual(x.Runs(), {})

  def testRunNamesRespected(self):
    x = event_multiplexer.EventMultiplexer({'run1': 'path1', 'run2': 'path2'})
    self.assertItemsEqual(sorted(x.Runs().keys()), ['run1', 'run2'])
    self.assertEqual(x._GetAccumulator('run1')._path, 'path1')
    self.assertEqual(x._GetAccumulator('run2')._path, 'path2')

  def testReload(self):
    x = event_multiplexer.EventMultiplexer({'run1': 'path1', 'run2': 'path2'})
    self.assertFalse(x._GetAccumulator('run1').reload_called)
    self.assertFalse(x._GetAccumulator('run2').reload_called)
    x.Reload()
    self.assertTrue(x._GetAccumulator('run1').reload_called)
    self.assertTrue(x._GetAccumulator('run2').reload_called)

  def testAutoUpdate(self):
    x = event_multiplexer.EventMultiplexer({'run1': 'path1', 'run2': 'path2'})
    x.AutoUpdate(5)
    self.assertTrue(x._GetAccumulator('run1').autoupdate_called)
    self.assertEqual(x._GetAccumulator('run1').autoupdate_interval, 5)
    self.assertTrue(x._GetAccumulator('run2').autoupdate_called)
    self.assertEqual(x._GetAccumulator('run2').autoupdate_interval, 5)

  def testScalars(self):
    x = event_multiplexer.EventMultiplexer({'run1': 'path1', 'run2': 'path2'})

    run1_actual = x.Scalars('run1', 'sv1')
    run1_expected = ['path1/sv1']

    self.assertEqual(run1_expected, run1_actual)

  def testExceptions(self):
    x = event_multiplexer.EventMultiplexer({'run1': 'path1', 'run2': 'path2'})
    with self.assertRaises(KeyError):
      x.Scalars('sv1', 'xxx')

  def testInitialization(self):
    x = event_multiplexer.EventMultiplexer()
    self.assertEqual(x.Runs(), {})
    x = event_multiplexer.EventMultiplexer({'run1': 'path1', 'run2': 'path2'})
    self.assertItemsEqual(x.Runs(), ['run1', 'run2'])
    self.assertEqual(x._GetAccumulator('run1')._path, 'path1')
    self.assertEqual(x._GetAccumulator('run2')._path, 'path2')

  def testAddRunsFromDirectory(self):
    x = event_multiplexer.EventMultiplexer()
    tmpdir = self.get_temp_dir()
    join = os.path.join
    fakedir = join(tmpdir, 'fake_accumulator_directory')
    realdir = join(tmpdir, 'real_accumulator_directory')
    self.assertEqual(x.Runs(), {})
    x.AddRunsFromDirectory(fakedir)
    self.assertEqual(x.Runs(), {}, 'loading fakedir had no effect')

    _CreateCleanDirectory(realdir)
    x.AddRunsFromDirectory(realdir)
    self.assertEqual(x.Runs(), {}, 'loading empty directory had no effect')

    path1 = join(realdir, 'path1')
    gfile.MkDir(path1)
    x.AddRunsFromDirectory(realdir)
    self.assertEqual(x.Runs(), {}, 'creating empty subdirectory had no effect')

    _AddEvents(path1)
    x.AddRunsFromDirectory(realdir)
    self.assertItemsEqual(x.Runs(), ['path1'], 'loaded run: path1')
    loader1 = x._GetAccumulator('path1')
    self.assertEqual(loader1._path, path1, 'has the correct path')

    path2 = join(realdir, 'path2')
    _AddEvents(path2)
    x.AddRunsFromDirectory(realdir)
    self.assertItemsEqual(x.Runs(), ['path1', 'path2'])
    self.assertEqual(x._GetAccumulator('path1'), loader1,
                     'loader1 not regenerated')

    path2_2 = join(path2, 'path2')
    _AddEvents(path2_2)
    x.AddRunsFromDirectory(realdir)
    self.assertItemsEqual(x.Runs(), ['path1', 'path2', 'path2/path2'])
    self.assertEqual(x._GetAccumulator('path2/path2')._path, path2_2,
                     'loader2 path correct')

  def testAddRunsFromDirectoryThatContainsEvents(self):
    x = event_multiplexer.EventMultiplexer()
    tmpdir = self.get_temp_dir()
    join = os.path.join
    realdir = join(tmpdir, 'event_containing_directory')

    _CreateCleanDirectory(realdir)

    self.assertEqual(x.Runs(), {})

    _AddEvents(realdir)
    x.AddRunsFromDirectory(realdir)
    self.assertItemsEqual(x.Runs(), ['.'])

    subdir = join(realdir, 'subdir')
    _AddEvents(subdir)
    x.AddRunsFromDirectory(realdir)
    self.assertItemsEqual(x.Runs(), ['.', 'subdir'])

  def testAddRunsFromDirectoryWithRunNames(self):
    x = event_multiplexer.EventMultiplexer()
    tmpdir = self.get_temp_dir()
    join = os.path.join
    realdir = join(tmpdir, 'event_containing_directory')

    _CreateCleanDirectory(realdir)

    self.assertEqual(x.Runs(), {})

    _AddEvents(realdir)
    x.AddRunsFromDirectory(realdir, 'foo')
    self.assertItemsEqual(x.Runs(), ['foo/.'])

    subdir = join(realdir, 'subdir')
    _AddEvents(subdir)
    x.AddRunsFromDirectory(realdir, 'foo')
    self.assertItemsEqual(x.Runs(), ['foo/.', 'foo/subdir'])

  def testAddRunsFromDirectoryWalksTree(self):
    x = event_multiplexer.EventMultiplexer()
    tmpdir = self.get_temp_dir()
    join = os.path.join
    realdir = join(tmpdir, 'event_containing_directory')

    _CreateCleanDirectory(realdir)
    _AddEvents(realdir)
    sub = join(realdir, 'subdirectory')
    sub1 = join(sub, '1')
    sub2 = join(sub, '2')
    sub1_1 = join(sub1, '1')
    _AddEvents(sub1)
    _AddEvents(sub2)
    _AddEvents(sub1_1)
    x.AddRunsFromDirectory(realdir)

    self.assertItemsEqual(x.Runs(), ['.',
                                     'subdirectory/1', 'subdirectory/2',
                                     'subdirectory/1/1'])

  def testAddRunsFromDirectoryThrowsException(self):
    x = event_multiplexer.EventMultiplexer()
    tmpdir = self.get_temp_dir()

    filepath = _AddEvents(tmpdir)
    with self.assertRaises(ValueError):
      x.AddRunsFromDirectory(filepath)

  def testAddRun(self):
    x = event_multiplexer.EventMultiplexer()
    x.AddRun('run1_path', 'run1')
    run1 = x._GetAccumulator('run1')
    self.assertEqual(sorted(x.Runs().keys()), ['run1'])
    self.assertEqual(run1._path, 'run1_path')

    x.AddRun('run1_path', 'run1')
    self.assertEqual(run1, x._GetAccumulator('run1'), 'loader not recreated')

    x.AddRun('run2_path', 'run1')
    new_run1 = x._GetAccumulator('run1')
    self.assertEqual(new_run1._path, 'run2_path')
    self.assertNotEqual(run1, new_run1)

    x.AddRun('runName3')
    self.assertItemsEqual(sorted(x.Runs().keys()), ['run1', 'runName3'])
    self.assertEqual(x._GetAccumulator('runName3')._path, 'runName3')

  def testAddRunMaintainsLoading(self):
    x = event_multiplexer.EventMultiplexer()
    x.Reload()
    x.AddRun('run1')
    x.AddRun('run2')
    self.assertTrue(x._GetAccumulator('run1').reload_called)
    self.assertTrue(x._GetAccumulator('run2').reload_called)

  def testAddRunMaintainsAutoUpdate(self):
    x = event_multiplexer.EventMultiplexer()
    x.AutoUpdate(5)
    x.AddRun('run1')
    x.AddRun('run2')
    self.assertTrue(x._GetAccumulator('run1').autoupdate_called)
    self.assertTrue(x._GetAccumulator('run2').autoupdate_called)
    self.assertEqual(x._GetAccumulator('run1').autoupdate_interval, 5)
    self.assertEqual(x._GetAccumulator('run2').autoupdate_interval, 5)

if __name__ == '__main__':
  googletest.main()
