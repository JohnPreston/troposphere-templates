################################################################################
#
# cfnmacro-vpc
#
################################################################################

ifndef VERBOSE
.SILENT:
endif

RM			= rm -f
ECHO			= echo -e
TAG			= etags
PIP			= pip
PYTHON			= python3
SHELL			= /bin/bash
WHICH                   = /usr/bin/which
WATCH                   = /usr/bin/watch
TEST                    = /usr/bin/test
ZIP			= /usr/bin/zip

SRC			= function.py		\
			  vpc.py		\
			  subnets_maths.py
AWS			= aws

VENV 			?= .venv
VENV_ACTIVATE		=. $(VENV)/bin/activate
ALIAS_NAME		?= $(shell bash -c 'read -p "Alias name: " alias; echo $$alias')

STACK			:=lambda-function-cfnmacro-vpc
FUNCTION_NAME		:=cfnmacro-vpc
ifndef BUCKET_NAME
BUCKET_NAME		:=ews-cf-templates-$(AWS_DEFAULT_REGION)
endif

export VIRTUAL_ENV 	:= $(abspath ${VENV})
export PATH 		:= ${VIRTUAL_ENV}/bin:${PATH}

all			: venv template package


${VENV}			:
			$(PYTHON) -m venv $@


venv-install		: requirements_dev.txt | ${VENV}
			$(PIP) install -U pip
			$(PIP) install --upgrade -r requirements_dev.txt

venv			:
			test -d ${VENV} || $(MAKE) venv-install
			$(VENV_ACTIVATE)
			$(WHICH) python


clean-template		:
			$(RM) $(FUNCTION_NAME).yml

clean			: clean-template
			$(RM) $(FUNCTION_NAME).zip


template		: clean-template package $(VENV_ACTIVATE)
			$(AWS) cloudformation package --s3-bucket $(BUCKET_NAME) \
			--template-file function_template.yml \
			--output-template-file $(FUNCTION_NAME).yml

package			: clean
			$(ZIP) -r9 $(FUNCTION_NAME).zip $(SRC)


create			: template $(VENV_ACTIVATE)
			$(AWS) cloudformation create-stack --stack-name $(STACK) \
			--template-body file://$(FUNCTION_NAME).yml \
			--capabilities CAPABILITY_AUTO_EXPAND CAPABILITY_IAM

update			: template publish $(VENV_ACTIVATE)
			$(AWS) cloudformation update-stack --stack-name $(STACK) \
			--template-body file://$(FUNCTION_NAME).yml \
			--capabilities CAPABILITY_AUTO_EXPAND CAPABILITY_IAM

delete			: clean-template
			$(AWS) cloudformation delete-stack --stack-name $(STACK)

validate		: $(VENV_ACTIVATE)
			$(AWS) cloudformation validate-template \
			--template-body file://$(FUNCTION_NAME).yml

events			: $(VENV_ACTIVATE)
			$(AWS) cloudformation describe-stack-events \
			--stack-name $(STACK) \
			--region $(AWS_REGION)

watch			:
			$(WATCH) --interval 1 "bash -c 'make events | head -40'"

.PHONY			: all venv venv-install clean clean-template package publish
