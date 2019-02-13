# coding: utf8

"""

"""

import abc

from nipype.pipeline.engine import Workflow


def get_subject_session_list(input_dir, ss_file=None, is_bids_dir=True, use_session_tsv=False):
    """Parses a BIDS or CAPS directory to get the subjects and sessions.

    This function lists all the subjects and sessions based on the content of
    the BIDS or CAPS directory or (if specified) on the provided
    subject-sessions TSV file.

    Args:
        input_dir: A BIDS or CAPS directory path.
        ss_file: A subjects-sessions file (.tsv format).
        is_bids_dir: Indicates if input_dir is a BIDS or CAPS directory
        use_session_tsv (boolean): Specify if the list uses the sessions listed in the sessions.tsv files

    Returns:
        subjects: A subjects list.
        sessions: A sessions list.
    """
    import clinica.iotools.utils.data_handling as cdh
    import pandas as pd
    import tempfile
    from time import time, strftime, localtime
    import os

    if not ss_file:
        output_dir = tempfile.mkdtemp()
        timestamp = strftime('%Y%m%d_%H%M%S', localtime(time()))
        tsv_file = '%s_subjects_sessions_list.tsv' % timestamp
        ss_file = os.path.join(output_dir, tsv_file)

        cdh.create_subs_sess_list(
            input_dir=input_dir,
            output_dir=output_dir,
            file_name=tsv_file,
            is_bids_dir=is_bids_dir,
            use_session_tsv=use_session_tsv)

    ss_df = pd.io.parsers.read_csv(ss_file, sep='\t')
    if 'participant_id' not in list(ss_df.columns.values):
        raise Exception('No participant_id column in TSV file.')
    if 'session_id' not in list(ss_df.columns.values):
        raise Exception('No session_id column in TSV file.')
    subjects = list(ss_df.participant_id)
    sessions = list(ss_df.session_id)

    return sessions, subjects


def postset(attribute, value):
    """Sets the attribute of an object after the execution.

    Args:
        attribute: An object's attribute to be set.
        value: A desired value for the object's attribute.

    Returns:
        A decorator executed after the decorated function is.
    """
    def postset_decorator(func):
        def func_wrapper(self, *args, **kwargs):
            res = func(self, *args, **kwargs)
            setattr(self, attribute, value)
            return res
        return func_wrapper
    return postset_decorator


class Pipeline(Workflow):
    """Clinica Pipeline class.

    This class overwrites the `Workflow` to integrate and encourage the
    use of BIDS and CAPS data structures as inputs and outputs of the pipelines
    developed for the Clinica software.

    The global architecture of a Clinica pipelines is as follow:
        [ Data Input Stream ]
                |
            [ Input ]
                |
            [[ Core ]] <- Could be one or more `npe.Node`s
                |
            [ Output ]
                |
        [ Data Output Stream ]

    Attributes:
        is_built (bool): Informs if the pipelines has been built or not.
        parameters (dict): Parameters of the pipelines.
        info (dict): Information presented in the associated `info.json` file.
        bids_layout (:obj:`BIDSLayout`): Object representing the BIDS directory.
        input_node (:obj:`npe.Node`): Identity interface connecting inputs.
        output_node (:obj:`npe.Node`): Identity interface connecting outputs.
        bids_directory (str): Directory used to read the data from, in BIDS.
        caps_directory (str): Directory used to read/write the data from/to,
            in CAPS.
        subjects (list): List of subjects defined in the `subjects.tsv` file.
            # TODO(@jguillon): Check the subjects-sessions file name.
        sessions (list): List of sessions defined in the `subjects.tsv` file.
        tsv_file (str): Path to the subjects-sessions `.tsv` file.
        info_file (str): Path to the associated `info.json` file.
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self, bids_directory=None, caps_directory=None, tsv_file=None, name=None):
        """Inits a Pipeline object.

        Args:
            bids_directory (optional): Path to a BIDS directory.
            caps_directory (optional): Path to a CAPS directory.
            tsv_file (optional): Path to a subjects-sessions `.tsv` file.
            name (optional): A pipelines name.
        """
        import inspect
        import os
        self._is_built = False
        self._bids_directory = bids_directory
        self._caps_directory = caps_directory
        self._verbosity = 'debug'
        self._tsv_file = tsv_file
        self._info_file = os.path.join(
            os.path.dirname(os.path.abspath(inspect.getfile(self.__class__))),
            'info.json')
        self._info = {}

        if name:
            self._name = name
        else:
            self._name = self.__class__.__name__
        self._parameters = {}

        if self._bids_directory is None:
            if self._caps_directory is None:
                raise IOError('%s does not contain BIDS nor CAPS directory' %
                              self._name)
            if not os.path.isdir(self._caps_directory):
                raise IOError('The CAPS parameter is not a folder (given path:%s)' %
                              self._caps_directory)

            self._sessions, self._subjects = get_subject_session_list(
                input_dir=self._caps_directory,
                ss_file=self._tsv_file,
                is_bids_dir=False
            )
        else:
            if not os.path.isdir(self._bids_directory):
                raise IOError('The BIDS parameter is not a folder (given path:%s)' %
                              self._bids_directory)
            self._sessions, self._subjects = get_subject_session_list(
                input_dir=self._bids_directory,
                ss_file=self._tsv_file,
                is_bids_dir=True
            )

        self.init_nodes()

    def init_nodes(self):
        """Inits the basic workflow and I/O nodes necessary before build.

        """
        import nipype.interfaces.utility as nutil
        import nipype.pipeline.engine as npe
        if self.get_input_fields():
            self._input_node = npe.Node(name="Input",
                                        interface=nutil.IdentityInterface(
                                            fields=self.get_input_fields(),
                                            mandatory_inputs=False))
        else:
            self._input_node = None

        if self.get_output_fields():
            self._output_node = npe.Node(name="Output",
                                         interface=nutil.IdentityInterface(
                                             fields=self.get_output_fields(),
                                             mandatory_inputs=False))
        else:
            self._output_node = None

        Workflow.__init__(self, self._name)
        if self.input_node:
            self.add_nodes([self.input_node])
        if self.output_node:
            self.add_nodes([self.output_node])

    def has_input_connections(self):
        """Checks if the Pipeline's input node has been connected.

        Returns:
            True if the input node is connected, False otherwise.
        """
        if self.input_node:
            return self._graph.in_degree(self.input_node) > 0
        else:
            return False

    def has_output_connections(self):
        """Checks if the Pipeline's output node has been connected.

        Returns:
            True if the output node is connected, False otherwise.
        """
        if self.output_node:
            return self._graph.out_degree(self.output_node) > 0
        else:
            return False

    @postset('is_built', True)
    def build(self):
        """Builds the core, input and output nodes of the Pipeline.

        This method first checks it has already been run. It then checks
        the pipelines dependencies and, in this order, builds the core nodes,
        the input node and, finally, the ouput node of the Pipeline.

        Since this method returns the concerned object, it can be chained to
        any other method of the Pipeline class.

        Returns:
            self: A Pipeline object.
        """
        if not self.is_built:
            self.check_dependencies()
            if not self.has_input_connections():
                self.build_input_node()
            self.build_core_nodes()
            if not self.has_output_connections():
                self.build_output_node()
        return self

    def run(self, plugin=None, plugin_args=None, update_hash=False):
        """Executes the Pipeline.

        It overwrites the default Workflow method to check if the
        Pipeline is built before running it. If not, it builds it and then
        run it.

        Args:
            Similar to those of Workflow.run.

        Returns:
            An execution graph (see Workflow.run).
        """
        if not self.is_built:
            self.build()
        self.check_size()
        return Workflow.run(self, plugin, plugin_args, update_hash)

    def load_info(self):
        """Loads the associated info.json file.

        Todos:
            - [ ] Raise an appropriate exception when the info file can't open

        Raises:
            None. # TODO(@jguillon)

        Returns:
            self: A Pipeline object.
        """
        import json
        with open(self.info_file) as info_file:
            self.info = json.load(info_file)
        return self

    def check_dependencies(self):
        """Checks if listed dependencies are present.

        Loads the pipelines related `info.json` file and check each one of the
        dependencies listed in the JSON "dependencies" field. Its raises
        exception if a program in the list does not exist or if environment
        variables are not properly defined.

        Todos:
            - [ ] MATLAB toolbox dependency checking
            - [x] check MATLAB
            - [ ] Clinica pipelines dependency checkings
            - [ ] Check dependencies version

        Raises:
            Exception: Raises an exception when bad dependency types given in
            the `info.json` file are detected.

        Returns:
            self: A Pipeline object.
        """
        import clinica.utils.check_dependency as chk

        # Checking functions preparation
        check_software = {
            # 'matlab': chk.check_matlab,
            'ants': chk.check_ants,
            'spm': chk.check_spm,
            'freesurfer': chk.check_freesurfer,
            'fsl': chk.check_fsl,
            'mrtrix': chk.check_mrtrix,
            'matlab': chk.check_matlab
        }
        check_binary = chk.is_binary_present
        # check_toolbox = chk.is_toolbox_present
        # check_pipeline = chk.is_pipeline_present

        # Load the info.json file
        if not self.info:
            self.load_info()

        # Dependencies checking
        for d in self.info['dependencies']:
            if d['type'] == 'software':
                check_software[d['name']]()
            elif d['type'] == 'binary':
                check_binary(d['name'])
            elif d['type'] == 'toolbox':
                pass
            elif d['type'] == 'pipeline':
                pass
            else:
                raise Exception("Unknown dependency type: '%s'." % d['type'])

        self.check_custom_dependencies()

        return self

    def check_size(self):
        """ Checks if the pipeline has enough space on the disk for both
        working directory and caps directory

        Author : Arnaud Marcoux"""
        from os import statvfs
        from os.path import dirname, abspath, join
        from pandas import read_csv
        import warnings

        SYMBOLS = {
            'customary': ('B', 'K', 'M', 'G', 'T', 'P', 'E', 'Z', 'Y'),
            'customary_ext': (
                'byte', 'kilo', 'mega', 'giga', 'tera', 'peta', 'exa',
                'zetta', 'iotta'),
            'iec': ('Bi', 'Ki', 'Mi', 'Gi', 'Ti', 'Pi', 'Ei', 'Zi', 'Yi'),
            'iec_ext': ('byte', 'kibi', 'mebi', 'gibi', 'tebi', 'pebi', 'exbi',
                        'zebi', 'yobi'),
        }

        def bytes2human(n,
                        format='%(value).1f %(symbol)s',
                        symbols='customary'):
            """
            Convert n bytes into a human readable string based on format.
            symbols can be either "customary", "customary_ext", "iec" or "iec_ext",
            see: http://goo.gl/kTQMs

            License :
            Bytes-to-human / human-to-bytes converter.
            Based on: http://goo.gl/kTQMs
            Working with Python 2.x and 3.x.
            Author: Giampaolo Rodola' <g.rodola [AT] gmail [DOT] com>
            License: MIT
            """
            n = int(n)
            if n < 0:
                raise ValueError("n < 0")
            symbols = SYMBOLS[symbols]
            prefix = {}
            for i, s in enumerate(symbols[1:]):
                prefix[s] = 1 << (i + 1) * 10
            for symbol in reversed(symbols[1:]):
                if n >= prefix[symbol]:
                    value = float(n) / prefix[symbol]
                    return format % locals()
            return format % dict(symbol=symbols[0], value=n)

        def human2bytes(s):
            """
            Attempts to guess the string format based on default symbols
            set and return the corresponding bytes as an integer.
            When unable to recognize the format ValueError is raised.

            License :
            Bytes-to-human / human-to-bytes converter.
            Based on: http://goo.gl/kTQMs
            Working with Python 2.x and 3.x.
            Author: Giampaolo Rodola' <g.rodola [AT] gmail [DOT] com>
            License: MIT
            """
            init = s
            num = ""
            while s and s[0:1].isdigit() or s[0:1] == '.':
                num += s[0]
                s = s[1:]
            num = float(num)
            letter = s.strip()
            for name, sset in SYMBOLS.items():
                if letter in sset:
                    break
            else:
                if letter == 'k':
                    # treat 'k' as an alias for 'K' as per: http://goo.gl/kTQMs
                    sset = SYMBOLS['customary']
                    letter = letter.upper()
                else:
                    raise ValueError("can't interpret %r" % init)
            prefix = {sset[0]: 1}
            for i, s in enumerate(sset[1:]):
                prefix[s] = 1 << (i + 1) * 10
            return int(num * prefix[letter])

        # Get the number of sessions
        n_sessions = len(self.subjects)
        try:
            caps_stat = statvfs(self.caps_directory)
        except FileNotFoundError:
            # CAPS folder may not exist yet
            caps_stat = statvfs(dirname(self.caps_directory))
        try:
            wd_stat = statvfs(dirname(self.parameters['wd']))
        except (KeyError, FileNotFoundError):
            # Not all pipelines has a 'wd' parameter
            # todo : maybe more relevant to always take base_dir ?
            wd_stat = statvfs(dirname(self.base_dir))

        # Estimate space left on partition/disk/whatever caps and wd is located
        free_space_caps = caps_stat.f_bavail * caps_stat.f_frsize
        free_space_wd = wd_stat.f_bavail * wd_stat.f_frsize

        # space estimation file location
        info_pipelines = read_csv(join(dirname(abspath(__file__)),
                                       'space_required_by_pipeline.csv'),
                                  sep=';')
        pipeline_list = list(info_pipelines.pipeline_name)
        try:
            idx_pipeline = pipeline_list.index(self._name)
            space_needed_caps_1_session = info_pipelines.space_caps[idx_pipeline]
            space_needed_wd_1_session = info_pipelines.space_wd[idx_pipeline]
            space_needed_caps = n_sessions * human2bytes(space_needed_caps_1_session)
            space_needed_wd = n_sessions * human2bytes(space_needed_wd_1_session)
            error = ''
            if free_space_caps == free_space_wd:
                if space_needed_caps + space_needed_wd > free_space_wd:
                    # We assume this is the same disk
                    error = error \
                            + 'Space needed for CAPS and working directory (' \
                            + bytes2human(space_needed_caps + space_needed_wd) \
                            + ') is greater than what is left on your hard drive (' \
                            + bytes2human(free_space_wd) + ')'
            else:
                if space_needed_caps > free_space_caps:
                    error = error + ('Space needed for CAPS (' + bytes2human(space_needed_caps)
                                     + ') is greater than what is left on your hard '
                                     + 'drive (' + bytes2human(free_space_caps) + ')\n')
                if space_needed_wd > free_space_wd:
                    error = error + ('Space needed for working_directory ('
                                     + bytes2human(space_needed_wd) + ') is greater than what is left on your hard '
                                     + 'drive (' + bytes2human(free_space_wd) + ')\n')
            if error != '':
                raise RuntimeError(error)
        except ValueError:
            warnings.warn('No info on how much size the pipeline takes. '
                          + 'Running anyway...')

    @property
    def is_built(self): return self._is_built

    @is_built.setter
    def is_built(self, value): self._is_built = value

    @property
    def parameters(self): return self._parameters

    @parameters.setter
    def parameters(self, value):
        self._parameters = value
        # Need to rebuild input, output and core nodes
        self.is_built = False
        self.init_nodes()

    @property
    def info(self): return self._info

    @info.setter
    def info(self, value): self._info = value

    @property
    def bids_layout(self):
        from bids.grabbids import BIDSLayout
        return BIDSLayout(self.bids_directory)

    @property
    def input_node(self): return self._input_node

    @property
    def output_node(self): return self._output_node

    @property
    def bids_directory(self): return self._bids_directory

    @property
    def caps_directory(self): return self._caps_directory

    @property
    def subjects(self): return self._subjects

    @property
    def sessions(self): return self._sessions

    @property
    def tsv_file(self): return self._tsv_file

    @property
    def info_file(self): return self._info_file

    @abc.abstractmethod
    def build_core_nodes(self):
        """Builds the Pipeline's core nodes.

        This method should use and connect to the `Pipeline.input_node` one
        or more core `Node`s. The outputs of the core processing should then be
        connected to the `Pipeline.output_node`.
        """
        pass

    @abc.abstractmethod
    def build_input_node(self):
        """Builds the Pipeline's input data stream node.

        Warnings:
            This method does not modify the `Pipeline.input_node` (see the
            notes about the global architecture in the class documentation).
        """
        pass

    @abc.abstractmethod
    def build_output_node(self):
        """Builds the Pipeline's output data stream node.

        Warnings:
            This method does not modify the `Pipeline.output_node` (see the
            notes about the global architecture in the class documentation).
        """
        pass

    @abc.abstractmethod
    def get_input_fields(self):
        """Lists the input fields of the Pipeline.

        Returns:
            A list of strings defining the fields of the `IdentityInterface`
            of the `Pipeline.input_node`.
        """
        pass

    @abc.abstractmethod
    def get_output_fields(self):
        """Lists the output fields of the Pipeline.

        Returns:
            A list of strings defining the fields of the `IdentityInterface`
            of the `Pipeline.output_node`.
        """
        pass

    @abc.abstractmethod
    def check_custom_dependencies(self):
        """Checks dependencies provided by the developer.
        """
        pass
