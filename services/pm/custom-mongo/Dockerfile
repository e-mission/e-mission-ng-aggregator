from mongo:3.6
ENV DEBIAN_FRONTEND noninteractive
RUN apt-get update
RUN apt-get install python3 -y
RUN apt-get install apt-utils -y
ADD ecryptfs_setup.sh /ecryptfs_setup.sh 
RUN ./ecryptfs_setup.sh
ADD start_script.sh /start_script.sh
ADD mount_ecryptfs.sh /mount_ecryptfs.sh
ADD encrypt.py /encrypt.py
CMD ["./start_script.sh"] 
