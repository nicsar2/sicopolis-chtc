FROM ubuntu:22.04

RUN apt-get update && \
	apt-get install -y \
		gcc=4:11.2.0-1ubuntu1 \
		libomp-dev=1:14.0-55~exp2 \
		gfortran=4:11.2.0-1ubuntu1 \
		libnetcdf-dev=1:4.8.1-1 \
		netcdf-bin=1:4.8.1-1 \
		libnetcdff-dev=4.5.4+ds-1 \
		unzip \
		wget \
		make \
		nano \
		git

RUN cd /tmp && \
	wget https://www.ssisc.org/lis/dl/lis-2.1.8.zip && \
	unzip lis-2.1.8.zip && \
	rm lis-2.1.8.zip && \
	cd lis-2.1.8 && \
	sh ./configure && \
	make && \
	make install && \
	cd .. && \
	rm -r lis-2.1.8

RUN 
	git clone https://github.com/sicopolis/sicopolis.git && \
	cd /sicopolis && \
	./get_input_files.sh; \
	./copy_templates.sh && \
	sed -i 's|^export NETCDFHOME=/opt/netcdf$|export NETCDFHOME=/usr|' sico_configs.sh && \
	sed -i 's|^   LISHOME=/opt/lis$|   LISHOME=/usr/local/bin|' sico_configs.sh 

