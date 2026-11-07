import pytest
import ncs

PE_DEVICES = ['ios-0']
ISIS_AREA_TAG = '1'


@pytest.fixture(scope='session')
def maapi():
    with ncs.maapi.Maapi() as m:
        with ncs.maapi.Session(m, 'admin', 'python'):
            yield m

@pytest.fixture(scope='session', autouse=True)
def test_customer(maapi):
    """Create a test customer to satisfy the customer-name leafref; tear it down after the session."""
    with maapi.start_write_trans() as t:
        root = ncs.maagic.get_root(t)
        if 'pytest-customer' not in root.customers.customer:
            root.customers.customer.create('pytest-customer')
            t.apply()

    yield # yield pauses setup here; pytest runs all tests, then resumes below for teardown

    with maapi.start_write_trans() as t:
        root = ncs.maagic.get_root(t)
        if 'pytest-customer' in root.customers.customer:
            del root.customers.customer['pytest-customer']
            t.apply()

@pytest.fixture(scope='session', autouse=True)
def isis_instance(maapi):
    """The service requires 'router isis 1' to pre-exist on each PE. Create it where missing and
    remove only the instances this fixture created at teardown."""
    created = []
    with maapi.start_write_trans() as t:
        root = ncs.maagic.get_root(t)
        for name in PE_DEVICES:
            isis = root.devices.device[name].config.ios__router.isis_container.isis
            if ISIS_AREA_TAG not in isis:
                isis.create(ISIS_AREA_TAG)
                created.append(name)
        if created:
            t.apply()

    yield # yield pauses setup here; pytest runs all tests, then resumes below for teardown

    if created:
        with maapi.start_write_trans() as t:
            root = ncs.maagic.get_root(t)
            for name in created:
                del root.devices.device[name].config.ios__router.isis_container.isis[ISIS_AREA_TAG]
            t.apply()
