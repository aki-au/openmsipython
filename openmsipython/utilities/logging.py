#imports
import logging

class MyFormatter(logging.Formatter) :
    """
    Very small extension of the usual logging.Formatter to allow modification of format based on message content
    """

    def __init__(self,*args,**kwargs) :
        super().__init__(*args,**kwargs)

    def format(self, record):
        """
        If a message starts with a newline, start the actual logging line with the newline before any of the rest
        """
        formatted = ''
        if record.msg.startswith('\n') :
            record.msg = record.msg.lstrip('\n')
            formatted+='\n'
        formatted+=super().format(record)
        return formatted

class Logger :
    """
    Class for a general logger. Logs messages and raises exceptions
    """

    @property
    def formatter(self):
        return MyFormatter('[%(name)s at %(asctime)s] %(message)s','%Y-%m-%d %H:%M:%S')

    def __init__(self,logger_name=None,streamlevel=logging.DEBUG,logger_filepath=None,filelevel=logging.INFO) :
        """
        name = the name for this logger to use (probably something like the top module that owns it)
        """
        self._name = logger_name
        if self._name is None :
            self._name = self.__name__
        self._logger_obj = logging.getLogger(self._name)
        self._logger_obj.setLevel(logging.DEBUG)
        self._streamhandler = logging.StreamHandler()
        self._streamhandler.setLevel(streamlevel)
        self._streamhandler.setFormatter(self.formatter)
        self._logger_obj.addHandler(self._streamhandler)
        self._filehandler = None
        if logger_filepath is not None :
            self.add_file_handler(logger_filepath)

    #set the level of the underlying logger
    def set_level(self,level) :
        self._logger_obj.setLevel(level)
    #set the level of the streamhandler
    def set_stream_level(self,level) :
        self._streamhandler.setLevel(level)
    #set the level of the filehandler
    def set_file_level(self,level) :
        if self._filehandler is None :
            errmsg = f'ERROR: Logger {self._name} does not have a filehandler set but set_file_level was called!'
            raise RuntimeError(errmsg)
        self._filehandler.setLevel(level)

    #add a filehandler to the logger
    def add_file_handler(self,filepath,level=logging.INFO) :
        if not filepath.is_file() :
            if not filepath.parent.is_dir() :
                filepath.parent.mkdir(parents=True)
            filepath.touch()
        self._filehandler = logging.FileHandler(filepath)
        self._filehandler.setLevel(level)
        self._filehandler.setFormatter(self.formatter)
        self._logger_obj.addHandler(self._filehandler)

    #methods for logging different levels of messages

    def debug(self,msg,*args,**kwargs) :
        self._logger_obj.debug(msg,*args,**kwargs)
    
    def info(self,msg,*args,**kwargs) :
        self._logger_obj.info(msg,*args,**kwargs)
    
    def warning(self,msg,*args,**kwargs) :
        if not msg.startswith('WARNING:') :
            msg = f'WARNING: {msg}'
        self._logger_obj.warning(msg)

    #log an error message and optionally raise an exception with the same message
    def error(self,msg,exception_type=None,*args,**kwargs) :
        if not msg.startswith('ERROR:') :
            msg = f'ERROR: {msg}'
        self._logger_obj.error(msg,*args,**kwargs)
        if exception_type is not None :
            raise exception_type(msg)

class LogOwner :
    """
    Any subclasses extending this one will have access to a Logger defined by the first class in the MRO to extend it
    """

    @property
    def logger(self) :
        return self.__logger

    def __init__(self,*args,
                 logger=None,logger_name=None,streamlevel=logging.DEBUG,logger_file=None,filelevel=logging.INFO,
                 **other_kwargs) :
        if logger is not None :
            self.__logger = logger
        else :
            if logger_name is None :
                logger_name = self.__class__.__name__
            logger_filepath = logger_file
            if logger_file is not None and logger_file.is_dir() :
                logger_filepath = logger_file / f'{self.__class__.__name__}.log'
            self.__logger = Logger(logger_name,streamlevel,logger_filepath,filelevel)
        super().__init__(*args,**other_kwargs)
