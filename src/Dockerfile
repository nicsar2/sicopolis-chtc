FROM ubuntu:22.04

ENV LIS_VERSION=2.1.8
ENV LISDIR=/opt/lis
ENV NETCDF_PATH=/usr
ENV FC=gfortran

RUN apt-get update && \
	apt-get install -y \
		gcc=4:11.2.0-1ubuntu1 \
		libomp-dev=1:14.0-55~exp2 \
		gfortran=4:11.2.0-1ubuntu1 \
		libnetcdf-dev=1:4.8.1-1 \
		netcdf-bin=1:4.8.1-1 \
		libnetcdff-dev=4.5.4+ds-1 \
		unzip \
		tar \
		pigz \
		wget \
		make \
		nano \
		git

RUN cd /tmp && \
	wget https://www.ssisc.org/lis/dl/lis-$LIS_VERSION.zip && \
	unzip lis-$LIS_VERSION.zip && \
	rm lis-$LIS_VERSION.zip && \
	cd lis-$LIS_VERSION && \
	sh ./configure --prefix=${LISDIR} --libdir=${LISDIR}/lib \
	    --enable-fortran --enable-f90 \
	    --enable-omp --enable-saamg --enable-fma \
	    CC=gcc FC=gfortran F77=gfortran \
	    CFLAGS="-mcmodel=medium" CPPFLAGS="-mcmodel=medium" \
	    FCFLAGS="-mcmodel=medium" FFLAGS="-mcmodel=medium" &&\
	make && \
	make check &&\
	make install && \
	cd .. && \
	rm -r lis-$LIS_VERSION
