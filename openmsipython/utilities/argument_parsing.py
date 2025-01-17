#imports
import pathlib, math, uuid
from argparse import ArgumentParser
from ..data_file_io.config import RUN_OPT_CONST
from .config import UTIL_CONST

#################### MISC. FUNCTIONS ####################

#convert a string or path argument into a path to a file, checking if it exists
def existing_file(argstring) :
    if pathlib.Path.is_file(pathlib.Path(argstring)) :
        return pathlib.Path(argstring).resolve()
    raise FileNotFoundError(f'ERROR: file {argstring} does not exist!')

#convert a string or path argument into a directory path, checking if it exists
def existing_dir(argstring) :
    if pathlib.Path.is_dir(pathlib.Path(argstring)) :
        return pathlib.Path(argstring).resolve()
    raise FileNotFoundError(f'ERROR: directory {argstring} does not exist!')

#convert a string or path argument into a directory path, creating it if necessary
def create_dir(argstring) :
    if argstring is None : #Then the argument wasn't given and nothing should be done
        return None
    if pathlib.Path.is_dir(pathlib.Path(argstring)) :
        return pathlib.Path(argstring).resolve()
    try :
        pathlib.Path.mkdir(pathlib.Path(argstring),exist_ok=True)
        return pathlib.Path(argstring).resolve()
    except Exception as e :
        raise RuntimeError(f'ERROR: failed to create directory with name {argstring}! error: {e}')

#convert a string or path argument into a config file path (raise an exception if the file can't be found)
def config_path(configarg) :
    if isinstance(configarg,str) and '.' not in configarg :
        configarg+=UTIL_CONST.CONFIG_FILE_EXT
    if pathlib.Path.is_file(pathlib.Path(configarg)) :
        return pathlib.Path(configarg).resolve()
    if pathlib.Path.is_file(UTIL_CONST.CONFIG_FILE_DIR / configarg) :
        return (UTIL_CONST.CONFIG_FILE_DIR / configarg).resolve()
    raise ValueError(f'ERROR: config argument {configarg} is not a recognized config file!')

#make sure a given value is a nonzero integer power of two (or can be converted to one)
def int_power_of_two(argval) :
    if not isinstance(argval,int) :
        try :
            argval=int(argval)
        except Exception as e :
            raise ValueError(f'ERROR: could not convert {argval} to an integer in int_power_of_two! Exception: {e}')
    if argval<=0 or math.ceil(math.log2(argval))!=math.floor(math.log2(argval)) :
        raise ValueError(f'ERROR: invalid argument: {argval} must be a (nonzero) power of two!')
    return argval

#make sure a given value is a positive integer
def positive_int(argval) :
    try :
        argval = int(argval)
    except Exception as e :
        raise ValueError(f'ERROR: could not convert {argval} to an integer in positive_int! Exception: {e}')
    if (not isinstance(argval,int)) or (argval<1) :
        raise ValueError(f'ERROR: invalid argument: {argval} must be a positive integer!')
    return argval

#################### MYARGUMENTPARSER CLASS ####################

class MyArgumentParser(ArgumentParser) :
    """
    Class to make it easier to get an ArgumentParser with some commonly-used arguments in it
    """

    ARGUMENTS = {
        'filepath':
            ['positional',{'type':existing_file,'help':'Path to the data file to use'}],
        'output_dir':
            ['positional',{'type':create_dir,'help':'Path to the directory to put output in'}],
        'upload_dir':
            ['positional',{'type':existing_dir,'help':'Path to the directory to watch for files to upload'}],
        'config':
            ['optional',{'default':RUN_OPT_CONST.DEFAULT_CONFIG_FILE,'type':config_path,
                         'help':f'''Name of config file to use in {UTIL_CONST.CONFIG_FILE_DIR.resolve()}, 
                                    or path to a file in a different location'''}],
        'topic_name':
            ['optional',{'default':RUN_OPT_CONST.DEFAULT_TOPIC_NAME,
                         'help':'Name of the topic to produce to or consume from'}],
        'n_threads':
            ['optional',{'default':UTIL_CONST.DEFAULT_N_THREADS,'type':positive_int,
                         'help':'Maximum number of threads to use'}],
        'chunk_size':
            ['optional',{'default':RUN_OPT_CONST.DEFAULT_CHUNK_SIZE,'type':int_power_of_two,
                         'help':'''Max size (in bytes) of chunks into which files should be broken 
                                   as they are uploaded'''}],
        'queue_max_size':
            ['optional',{'default':RUN_OPT_CONST.DEFAULT_MAX_UPLOAD_QUEUE_SIZE,'type':int,
                         'help':'''Maximum number of items to allow in the upload queue at a time. 
                                 Use to limit RAM usage or throttle production rate if necessary.'''}],
        'update_seconds':
            ['optional',{'default':UTIL_CONST.DEFAULT_UPDATE_SECONDS,'type':int,
                         'help':'''Number of seconds between printing a "." to the console 
                                   to indicate the program is alive'''}],
        'new_files_only':
            ['optional',{'action':'store_true',
                         'help':'''Add this flag to only upload files added to the directory after 
                                   this code is already running (by default files already existing 
                                   in the directory at startup will be uploaded as well)'''}],
        'consumer_group_ID':
            ['optional',{'default':str(uuid.uuid1()),
                         'help':'ID to use for all consumers in the group'}],
        'pdv_plot_type':
            ['optional',{'choices':['spall','velocity'],'default':'spall',
                         'help':'Type of analysis to perform ("spall" or "velocity")'}],
        'optional_output_dir':
            ['optional',{'type':create_dir,
                         'help':'Optional path to directory to put output in'}],
        'service_name':
            ['positional',{'help':'The name of the service to work with'}],
        'run_mode':
            ['positional',{'choices':['start','status','stop','remove','stop_and_remove'],
                           'help':'What to do with the service'}],
        'remove_env_vars':
            ['optional',{'action':'store_true',
                         'help':'''Add this flag to also remove username/password environment variables 
                                   when removing a Service'''}],
    }

    #################### OVERLOADED FUNCTIONS ####################

    def __init__(self,*args,**kwargs) :
        super().__init__(*args,**kwargs)
        self.__subparsers_action_obj = None
        self.__subparsers = {}

    def add_subparsers(self,*args,**kwargs) :
        """
        Overloaded from base class; MyArgumentParser actually owns its subparsers
        """
        if self.__subparsers_action_obj is not None or self.__subparsers!={} :
            raise RuntimeError('ERROR: add_subparsers called for an argument parser that already has subparsers!')
        self.__subparsers_action_obj = super().add_subparsers(*args,**kwargs)

    def parse_args(self,**kwargs) :
        """
        Overloaded from base class to catch errors in parsing arguments
        """
        try :
            return super().parse_args(**kwargs)
        except TypeError :
            self.print_usage()
            return None

    #################### UNIQUE FUNCTIONS ####################

    def add_arguments(self,*args,**kwargs) :
        """
        Add a group of common arguments to the parser
        args = names of arguments that should be added just as listed in ARGUMENTS above
        kwargs = dictionary whose keys are argument names like in args and whose values are default argument values
        """
        if len(args)<1 and len(kwargs)<1 :
            raise ValueError('ERROR: must specify at least one desired argument to create an argument parser!')
        for argname in args :
            argname_to_add, kwargs_for_arg = self.__get_argname_and_kwargs(argname)
            self.add_argument(argname_to_add,**kwargs_for_arg)
        for argname,argdefault in kwargs.items() :
            argname_to_add, kwargs_for_arg = self.__get_argname_and_kwargs(argname,argdefault)
            self.add_argument(argname_to_add,**kwargs_for_arg)

    def add_subparser(self,cmd,**kwargs) :
        """
        Add a subparser by calling add_parser using the subparser action object
        Returns the subparser
        Just a wrapper around the usual UI
        """
        if self.__subparsers_action_obj is None :
            errmsg = 'ERROR: add_subparser_arguments_for_class called for an argument parser that '
            errmsg+= 'has not added subparsers!'
            raise RuntimeError(errmsg)
        self.__subparsers[cmd] = self.__subparsers_action_obj.add_parser(cmd,**kwargs)
        return self.__subparsers[cmd]

    def add_subparser_arguments_from_class(self,class_to_add,**kwargs) :
        """
        Create a new subparser and add arguments from the given class to it
        class_to_add must inherit from Runnable to be able to get its arguments
        kwargs are passed to subparsers.add_parser
        """
        if self.__subparsers_action_obj is None :
            errmsg = 'ERROR: add_subparser_arguments_for_class called for an argument parser that '
            errmsg+= 'has not added subparsers!'
            raise RuntimeError(errmsg)
        class_name = class_to_add.__name__
        if class_name in self.__subparsers.keys() :
            errmsg = f'ERROR: subparser arguments for {class_name} have already been added to this argument parser!'
            raise RuntimeError(errmsg)
        self.__subparsers[class_name] = self.__subparsers_action_obj.add_parser(class_name,**kwargs)
        argnames, argnames_with_defaults = class_to_add.get_command_line_arguments()
        for argname in argnames :
            argname_to_add, kwargs_for_arg = self.__get_argname_and_kwargs(argname)
            self.__subparsers[class_name].add_argument(argname_to_add,**kwargs_for_arg)
        for argname,argdefault in argnames_with_defaults.items() :
            argname,kwargs = self.__get_argname_and_kwargs(argname,argdefault)
            self.__subparsers[class_name].add_argument(argname,**kwargs)

    def __get_argname_and_kwargs(self,argname,new_default=None) :
        """
        Return the name and kwargs dict for a particular argument

        argname = the given name of the argument, will be matched to a name in ARGUMENTS
        new_default = an optional parameter given to override the default already specified in ARGUMENTS
        """
        if argname in self.ARGUMENTS.keys() :
            if self.ARGUMENTS[argname][0]=='positional' :
                argname_to_add = argname 
            else :
                if argname.startswith('optional_') :
                    argname_to_add = f'--{argname[len("optional_"):]}'
                else :
                    argname_to_add = f'--{argname}'
            kwargs = self.ARGUMENTS[argname][1].copy()
            if new_default is not None :
                if ( 'default' in kwargs.keys() and 
                    type(new_default)!=type(kwargs['default']) ) :
                    errmsg = f'ERROR: new default value {new_default} for argument {argname} is of a different type '
                    errmsg+= f'than expected based on the old default ({self.ARGUMENTS[argname]["kwargs"]["default"]})!'
                    raise ValueError(errmsg)
                kwargs['default'] = new_default
            if 'default' in kwargs.keys() :
                if 'help' in kwargs.keys() :
                    kwargs['help']+=f" (default = {kwargs['default']})"
                else :
                    kwargs['help']=f"default = {kwargs['default']}"
            return argname_to_add, kwargs
        else :
            raise ValueError(f'ERROR: argument {argname} is not recognized as an option!')
