#imports
import traceback
from threading import Thread
from queue import Queue
from hashlib import sha512
from .data_file import DataFile
from ..utilities.runnable import Runnable
from ..utilities.misc import populated_kwargs
from ..my_kafka.my_producers import MySerializingProducer
from .config import RUN_OPT_CONST
from .utilities import produce_from_queue_of_file_chunks
from .data_file_chunk import DataFileChunk

class UploadDataFile(DataFile,Runnable) :
    """
    Class to represent a data file whose messages will be uploaded to a topic
    """

    #################### PROPERTIES ####################

    @property
    def select_bytes(self) :
        return []   # in child classes this can be a list of tuples of (start_byte,stop_byte) 
                    # in the file that will be the only ranges of bytes added when creating the list of chunks
    @property
    def rootdir(self) :
        return self.__rootdir
    @property
    def chunks_to_upload(self) :
        return self.__chunks_to_upload
    @property
    def to_upload(self):
        return self.__to_upload #whether or not this file will be considered when uploading some group of data files
    @property
    def fully_enqueued(self): #whether or not this file has had all of its chunks added to an upload queue somewhere
        return self.__fully_enqueued
    @property
    def waiting_to_upload(self): #whether or not this file is waiting for its upload to begin
        if (not self.__to_upload) or self.__fully_enqueued :
            return False
        if len(self.__chunks_to_upload)>0 :
            return False
        return True
    @property
    def upload_in_progress(self): #whether this file is in the process of being enqueued to be uploaded
        if (not self.__to_upload) or self.__fully_enqueued :
            return False
        if len(self.__chunks_to_upload)==0 :
            return False
        return True
    @property
    def upload_status_msg(self): #a message stating the file's name and status w.r.t. being enqueued to be uploaded 
        if self.__rootdir is None :
            msg = f'{self.filepath} '
        else :
            msg = f'{self.filepath.relative_to(self.__rootdir)} '
        if not self.__to_upload :
            msg+='(will not be uploaded)'
        elif self.__fully_enqueued :
            msg+='(fully enqueued)'
        elif self.upload_in_progress :
            msg+='(in progress)'
        elif self.waiting_to_upload :
            msg+='(waiting to be enqueued)'
        else :
            msg+='(status unknown)'
        return msg

    #################### PUBLIC FUNCTIONS ####################

    def __init__(self,*args,to_upload=True,rootdir=None,filename_append='',**kwargs) :
        """
        to_upload       = if False, the file will be ignored for purposes of uploading to a topic (default is True)
        rootdir         = path to the "root" directory that this file is in; anything in the path beyond it 
                          will be added to the DataFileChunk so that it will be reconstructed inside a subdirectory
        filename_append = a string that should be appended to the end of the filename stem to distinguish the file 
                          that's produced from its original file on disk
        """
        super().__init__(*args,**kwargs)
        self.__to_upload = to_upload
        if rootdir is None :
            self.__rootdir = self.filepath.parent
        else :
            self.__rootdir = rootdir
        self.__filename_append = filename_append
        self.__fully_enqueued = False
        self.__chunks_to_upload = []

    def add_chunks_to_upload_queue(self,queue,**kwargs) :
        """
        Add chunks of this file to a given upload queue. 
        If the file runs out of chunks it will be marked as fully enqueued.
        If the given queue is full this function will do absolutely nothing and will just return.

        Possible keyword arguments:
        n_threads  = the number of threads running during uploading; at most 5*this number of chunks will be added 
                     per call to this function if this argument isn't given, every chunk will be added
        chunk_size = the size of each file chunk in bytes 
                     (used to create the list of file chunks if it doesn't already exist)
                     the default value will be used if this argument isn't given
        """
        if self.__fully_enqueued :
            warnmsg = f'WARNING: add_chunks_to_upload_queue called for fully enqueued file {self.filepath}, '
            warnmsg+= 'nothing else will be added.'
            self.logger.warning(warnmsg)
            return
        if queue.full() :
            return
        if len(self.__chunks_to_upload)==0 :
            kwargs = populated_kwargs(kwargs,{'chunk_size': RUN_OPT_CONST.DEFAULT_CHUNK_SIZE},self.logger)
            try :
                self._build_list_of_file_chunks(kwargs['chunk_size'])
            except Exception :
                self.logger.info(traceback.format_exc())
                fp = self.filepath.relative_to(self.__rootdir) if self.__rootdir is not None else self.filepath
                errmsg = f'ERROR: was not able to break {fp} into chunks for uploading. '
                errmsg+= 'Check log lines above for details on what went wrong. File will not be uploaded.'
                self.logger.error(errmsg)
                self.__to_upload = False
                return
        if kwargs.get('n_threads') is not None :
            n_chunks_to_add = 5*kwargs['n_threads']
        else :
            n_chunks_to_add = len(self.__chunks_to_upload)
        ic = 0
        while len(self.__chunks_to_upload)>0 and ic<n_chunks_to_add :
            queue.put(self.__chunks_to_upload.pop(0))
            ic+=1
        if len(self.__chunks_to_upload)==0 :
            self.__fully_enqueued = True
    
    def upload_whole_file(self,config_path,topic_name,**kwargs) :
        """
        Chunk and upload an entire file on disk to a cluster's topic.

        config_path = path to the config file to use in defining the producer
        topic_name  = name of the topic to produce messages to
        
        Possible keyword arguments:
        n_threads  = the number of threads to run at once during uploading
        chunk_size = the size of each file chunk in bytes
        """
        #set the important variables
        kwargs = populated_kwargs(kwargs,
                                  {'n_threads': RUN_OPT_CONST.N_DEFAULT_UPLOAD_THREADS,
                                   'chunk_size': RUN_OPT_CONST.DEFAULT_CHUNK_SIZE,
                                  },self.logger)
        #start the producer
        producer = MySerializingProducer.from_file(config_path,logger=self.logger)
        startup_msg = f"Uploading entire file {self.filepath} to {topic_name} in {kwargs['chunk_size']} byte chunks "
        startup_msg+=f"using {kwargs['n_threads']} threads...."
        self.logger.info(startup_msg)
        #add all the chunks to the upload queue
        upload_queue = Queue()
        self.add_chunks_to_upload_queue(upload_queue,chunk_size=kwargs['chunk_size'])
        #add "None" to the queue for each thread as the final values
        for ti in range(kwargs['n_threads']) :
            upload_queue.put(None)
        #produce all the messages in the queue using multiple threads
        upload_threads = []
        for ti in range(kwargs['n_threads']) :
            t = Thread(target=produce_from_queue_of_file_chunks, args=(upload_queue,
                                                                       producer,
                                                                       topic_name,
                                                                       self.logger))
            t.start()
            upload_threads.append(t)
        #join the threads
        for ut in upload_threads :
            ut.join()
        self.logger.info('Waiting for all enqueued messages to be delivered (this may take a moment)....')
        producer.flush() #don't leave the function until all messages have been sent/received
        self.logger.info('Done!')

    #################### PRIVATE HELPER FUNCTIONS ####################

    def _build_list_of_file_chunks(self,chunk_size) :
        """
        Build the full list of DataFileChunks for this file given a chunk size (in bytes)
        """
        #first make sure the choices of select_bytes are valid if necessary 
        #and sort them by their start byte to keep the file hash in order
        if self.select_bytes!=[] :
            if type(self.select_bytes)!=list :
                self.logger.error(f'ERROR: select_bytes={self.select_bytes} but is expected to be a list!',ValueError)
            for sbt in self.select_bytes :
                if type(sbt)!=tuple or len(sbt)!=2 :
                    errmsg = f'ERROR: found {sbt} in select_bytes but all elements are expected to be two-entry tuples!'
                    self.logger.error(errmsg,ValueError)
                elif sbt[0]>=sbt[1] :
                    errmsg = f'ERROR: found {sbt} in select_bytes but start byte cannot be >= stop byte!'
                    self.logger.error(errmsg,ValueError)
            sorted_select_bytes = sorted(self.select_bytes,key=lambda x: x[0])
        #start a hash for the file and the lists of chunks
        file_hash = sha512()
        chunks = []
        isb = 0 #index for the current sorted_select_bytes entry if necessary
        #read the binary data in the file as chunks of the given size, adding each chunk to the list 
        with open(self.filepath,'rb') as fp :
            chunk_offset = 0
            file_offset = 0 if self.select_bytes==[] else sorted_select_bytes[isb][0]
            n_bytes_to_read = chunk_size 
            if self.select_bytes!=[] :
                n_bytes_to_read = min(chunk_size,sorted_select_bytes[isb][1]-file_offset)
            chunk = fp.read(n_bytes_to_read)
            while len(chunk) > 0 :
                file_hash.update(chunk)
                chunk_hash = sha512()
                chunk_hash.update(chunk)
                chunk_hash = chunk_hash.digest()
                chunk_length = len(chunk)
                chunks.append([chunk_hash,file_offset,chunk_offset,chunk_length])
                chunk_offset += chunk_length
                file_offset += chunk_length
                if self.select_bytes!=[] and file_offset==sorted_select_bytes[isb][1] :
                    isb+=1
                    if isb>(len(sorted_select_bytes)-1) :
                        break
                    file_offset=sorted_select_bytes[isb][0]
                n_bytes_to_read = chunk_size 
                if self.select_bytes!=[] :
                    n_bytes_to_read = min(chunk_size,sorted_select_bytes[isb][1]-file_offset)
                fp.seek(file_offset)
                chunk = fp.read(n_bytes_to_read)
        file_hash = file_hash.digest()
        self.logger.info(f'File {self.filepath} has a total of {len(chunks)} chunks')
        #add all the chunks to the final list as DataFileChunk objects
        for ic,c in enumerate(chunks,start=1) :
            self.__chunks_to_upload.append(DataFileChunk(self.filepath,self.filename,file_hash,
                                                         c[0],c[1],c[2],c[3],ic,len(chunks),
                                                         rootdir=self.__rootdir,filename_append=self.__filename_append))

    #################### CLASS METHODS ####################

    @classmethod
    def get_command_line_arguments(cls) :
        args = ['filepath','config','topic_name','chunk_size']
        kwargs = {'n_threads':RUN_OPT_CONST.N_DEFAULT_UPLOAD_THREADS}
        return args,kwargs

    @classmethod
    def run_from_command_line(cls,args=None) :
        """
        Run the upload data file directly from the command line
        """
        #make the argument parser
        parser = cls.get_argument_parser()
        args = parser.parse_args(args=args)
        #make the DataFile for the single specified file
        upload_file = cls(args.filepath)
        #chunk and upload the file
        upload_file.upload_whole_file(args.config,args.topic_name,
                                      n_threads=args.n_threads,
                                      chunk_size=args.chunk_size)
        upload_file.logger.info(f'Done uploading {args.filepath}')


#################### MAIN METHOD TO RUN FROM COMMAND LINE ####################

def main(args=None) :
    UploadDataFile.run_from_command_line(args)

if __name__=='__main__' :
    main()
