# -*- mode: python; python-indent: 4 -*-


from ncs.application import Application, Service

from .completion import InterfaceCompletion
from .context import ServiceContext
from .dia import Dia


class ServiceCallbacks(Service):
    @Service.create
    def cb_create(self, tctx, root, service, proplist):
        self.log.info(f"Service create(service={service._path})")
        ctx = ServiceContext(log=self.log, root=root, service=service)
        Dia(ctx).configure()


class Main(Application):
    def setup(self):
        self.log.info("Main RUNNING")
        self.register_service("dia-servicepoint", ServiceCallbacks)
        self.register_action("dia-interface-name", InterfaceCompletion)

    def teardown(self):
        self.log.info("Main FINISHED")
