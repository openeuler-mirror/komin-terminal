MODULES := komind
PP_FILES := $(MODULES:%=%.pp)

SHAREDIR ?= /usr/share/selinux/devel
include $(SHAREDIR)/Makefile

clean:
	rm -f *.pp *.tmp
