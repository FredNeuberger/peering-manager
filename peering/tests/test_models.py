import ipaddress

from django.test import TestCase

from peering.constants import (
    COMMUNITY_TYPE_INGRESS,
    COMMUNITY_TYPE_EGRESS,
    PLATFORM_JUNOS,
    ROUTING_POLICY_TYPE_IMPORT,
    ROUTING_POLICY_TYPE_EXPORT,
)
from peering.models import (
    AutonomousSystem,
    Community,
    InternetExchange,
    InternetExchangePeeringSession,
    Router,
    RoutingPolicy,
)


class AutonomousSystemTestCase(TestCase):
    def test_does_exist(self):
        asn = 29467

        # AS should not exist
        autonomous_system = AutonomousSystem.does_exist(asn)
        self.assertEqual(None, autonomous_system)

        # Create the AS
        new_as = AutonomousSystem.objects.create(asn=asn, name="LuxNetwork S.A.")

        # AS must exist
        autonomous_system = AutonomousSystem.does_exist(asn)
        self.assertEqual(asn, new_as.asn)

    def test_create_from_peeringdb(self):
        asn = 29467

        # Illegal ASN
        self.assertIsNone(AutonomousSystem.create_from_peeringdb(64500))

        # Must not exist at first
        self.assertIsNone(AutonomousSystem.does_exist(asn))

        # Create the AS
        autonomous_system1 = AutonomousSystem.create_from_peeringdb(asn)
        self.assertEqual(asn, autonomous_system1.asn)

        # Must exist now
        self.assertEqual(asn, AutonomousSystem.does_exist(asn).asn)

        # Must not rise error, just return the AS
        autonomous_system2 = AutonomousSystem.create_from_peeringdb(asn)
        self.assertEqual(asn, autonomous_system2.asn)

        # Must exist now also
        self.assertEqual(asn, AutonomousSystem.does_exist(asn).asn)

    def test_synchronize_with_peeringdb(self):
        # Create legal AS to sync with PeeringDB
        asn = 29467
        autonomous_system = AutonomousSystem.create_from_peeringdb(asn)
        self.assertEqual(asn, autonomous_system.asn)
        self.assertTrue(autonomous_system.synchronize_with_peeringdb())

        # Create illegal AS to fail sync with PeeringDB
        asn = 64500
        autonomous_system = AutonomousSystem.objects.create(asn=asn, name="Test")
        self.assertEqual(asn, autonomous_system.asn)
        self.assertFalse(autonomous_system.synchronize_with_peeringdb())

    def test__str__(self):
        asn = 64500
        name = "Test"
        expected = "AS{} - {}".format(asn, name)
        autonomous_system = AutonomousSystem.objects.create(asn=asn, name=name)

        self.assertEqual(expected, str(autonomous_system))


class CommunityTestCase(TestCase):
    def test_create(self):
        community_list = [
            {"name": "Test", "value": "64500:1", "type": None, "str": "Test"},
            {
                "name": "Test",
                "value": "64500:1",
                "type": COMMUNITY_TYPE_EGRESS,
                "str": "Test",
            },
        ]

        for details in community_list:
            if details["type"]:
                community = Community.objects.create(
                    name=details["name"], value=details["value"], type=details["type"]
                )
            else:
                community = Community.objects.create(
                    name=details["name"], value=details["value"]
                )

            self.assertIsNotNone(community)
            self.assertEqual(details["name"], community.name)
            self.assertEqual(details["value"], community.value)
            self.assertEqual(details["type"] or COMMUNITY_TYPE_INGRESS, community.type)
            self.assertEqual(details["str"], str(community))

    def test_get_type_html(self):
        expected = [
            '<span class="badge badge-info">'
            '<i class="fas fa-arrow-circle-up"></i> Egress</span>',
            '<span class="badge badge-info">'
            '<i class="fas fa-arrow-circle-down"></i> Ingress</span>',
            '<span class="badge badge-secondary">'
            '<i class="fas fa-ban"></i> Unknown</span>',
        ]
        community_types = [COMMUNITY_TYPE_EGRESS, COMMUNITY_TYPE_INGRESS, "unknown"]

        for i in range(len(community_types)):
            self.assertEqual(
                expected[i],
                Community.objects.create(
                    name="test{}".format(i),
                    value="64500:{}".format(i),
                    type=community_types[i],
                ).get_type_html(),
            )


class InternetExchangeTestCase(TestCase):
    def test_is_peeringdb_valid(self):
        ix = InternetExchange.objects.create(name="Test", slug="test")

        # Not linked with PeeringDB but considered as valid
        self.assertTrue(ix.is_peeringdb_valid())

        # Set invalid ID, must result in false
        ix.peeringdb_id = 14658
        ix.save()
        self.assertFalse(ix.is_peeringdb_valid())

        # Set valid ID, must result in true
        ix.peeringdb_id = 29146
        ix.save()
        self.assertTrue(ix.is_peeringdb_valid())

    def test_get_peeringdb_id(self):
        # Expected results
        expected = [0, 0, 0, 0, 29146, 29146, 29146]

        # Test data
        data = [
            {
                # No IP addresses
            },
            {"ipv6_address": "2001:db8::1"},
            {"ipv4_address": "192.168.168.1"},
            {"ipv6_address": "2001:db8::1", "ipv4_address": "192.168.168.1"},
            {"ipv6_address": "2001:7f8:1::a502:9467:1"},
            {"ipv4_address": "80.249.212.207"},
            {
                "ipv6_address": "2001:7f8:1::a502:9467:1",
                "ipv4_address": "80.249.212.207",
            },
        ]

        # Run test cases
        for i in range(len(expected)):
            ixp = InternetExchange.objects.create(
                name="Test {}".format(i), slug="test_{}".format(i), **data[i]
            )
            self.assertEqual(expected[i], ixp.get_peeringdb_id())

    def test_import_peering_sessions(self):
        # Expected results
        expected = [
            # First case
            (1, 1, []),
            # Second case
            (0, 1, []),
            # Third case
            (0, 1, []),
            # Fourth case
            (0, 0, []),
        ]

        session_lists = [
            # First case, one new session with one new AS
            [{"ip_address": ipaddress.ip_address("2001:db8::1"), "remote_asn": 29467}],
            # Second case, one new session with one known AS
            [{"ip_address": ipaddress.ip_address("192.168.0.1"), "remote_asn": 29467}],
            # Third case, new IPv4 session on another IX but with an IP that
            # has already been used
            [{"ip_address": ipaddress.ip_address("192.168.0.1"), "remote_asn": 29467}],
            # Fourth case, new IPv4 session with IPv6 prefix
            [{"ip_address": ipaddress.ip_address("192.168.2.1"), "remote_asn": 29467}],
        ]

        prefix_lists = [
            # First case
            [ipaddress.ip_network("2001:db8::/64")],
            # Second case
            [ipaddress.ip_network("192.168.0.0/24")],
            # Third case
            [ipaddress.ip_network("192.168.0.0/24")],
            # Fourth case
            [ipaddress.ip_network("2001:db8::/64")],
        ]

        # Run test cases
        for i in range(len(expected)):
            ixp = InternetExchange.objects.create(
                name="Test {}".format(i), slug="test_{}".format(i)
            )
            self.assertEqual(
                expected[i],
                ixp._import_peering_sessions(session_lists[i], prefix_lists[i]),
            )
            self.assertEqual(expected[i][1], len(ixp.get_peering_sessions()))

    def test_generate_configuration(self):
        expected = [
            {
                "ip_version": 6,
                "peers": {
                    1: {
                        "as_name": "Test 1",
                        "max_prefixes": 0,
                        "sessions": [
                            {
                                "ip_address": "2001:db8::1",
                                "password": False,
                                "enabled": True,
                                "is_route_server": False,
                                "export_routing_policies": [],
                                "import_routing_policies": [],
                            }
                        ],
                    },
                    2: {
                        "as_name": "Test 2",
                        "max_prefixes": 0,
                        "sessions": [
                            {
                                "ip_address": "2001:db8::2",
                                "password": False,
                                "enabled": True,
                                "is_route_server": False,
                                "export_routing_policies": [],
                                "import_routing_policies": [],
                            }
                        ],
                    },
                    3: {
                        "as_name": "Test 3",
                        "max_prefixes": 0,
                        "sessions": [
                            {
                                "ip_address": "2001:db8::3",
                                "password": False,
                                "enabled": True,
                                "is_route_server": False,
                                "export_routing_policies": [],
                                "import_routing_policies": [],
                            }
                        ],
                    },
                    4: {
                        "as_name": "Test 4",
                        "max_prefixes": 0,
                        "sessions": [
                            {
                                "ip_address": "2001:db8::4",
                                "password": False,
                                "enabled": True,
                                "is_route_server": False,
                                "export_routing_policies": [],
                                "import_routing_policies": [],
                            }
                        ],
                    },
                    5: {
                        "as_name": "Test 5",
                        "max_prefixes": 0,
                        "sessions": [
                            {
                                "ip_address": "2001:db8::5",
                                "password": False,
                                "enabled": True,
                                "is_route_server": False,
                                "export_routing_policies": [],
                                "import_routing_policies": [],
                            }
                        ],
                    },
                },
            },
            {"ip_version": 4, "peers": {}},
        ]

        internet_exchange = InternetExchange.objects.create(name="Test", slug="test")
        for i in range(1, 6):
            InternetExchangePeeringSession.objects.create(
                autonomous_system=AutonomousSystem.objects.create(
                    asn=i, name="Test {}".format(i)
                ),
                internet_exchange=internet_exchange,
                ip_address="2001:db8::{}".format(i),
            )
        values = internet_exchange._generate_configuration_variables()
        self.assertEqual(values["peering_groups"], expected)


class InternetExchangePeeringSessionTestCase(TestCase):
    def test_does_exist(self):
        # No session, must expect None
        self.assertIsNone(InternetExchangePeeringSession.does_exist())

        # Prepare objects and create a peering session
        autonomous_system0 = AutonomousSystem.objects.create(asn=64500, name="Test")
        internet_exchange0 = InternetExchange.objects.create(name="Test0", slug="test0")
        peering_session0 = InternetExchangePeeringSession.objects.create(
            autonomous_system=autonomous_system0,
            internet_exchange=internet_exchange0,
            ip_address="2001:db8::1",
        )

        # Make sure that the session has been created
        self.assertIsNotNone(peering_session0)
        # Make sure that the session is returned by calling does_exist()
        # without arguments (only one session in the database)
        self.assertIsNotNone(InternetExchangePeeringSession.does_exist())
        # Make sure we can retrieve the session with its IP
        self.assertEqual(
            peering_session0,
            InternetExchangePeeringSession.does_exist(ip_address="2001:db8::1"),
        )
        # Make sure we can retrieve the session with its IX
        self.assertEqual(
            peering_session0,
            InternetExchangePeeringSession.does_exist(
                internet_exchange=internet_exchange0
            ),
        )
        # Make sure we can retrieve the session with AS
        self.assertEqual(
            peering_session0,
            InternetExchangePeeringSession.does_exist(
                autonomous_system=autonomous_system0
            ),
        )

        # Create another peering session
        peering_session1 = InternetExchangePeeringSession.objects.create(
            autonomous_system=autonomous_system0,
            internet_exchange=internet_exchange0,
            ip_address="192.168.1.1",
        )

        # Make sure that the session has been created
        self.assertIsNotNone(peering_session1)
        # More than one session, must expect None
        self.assertIsNone(InternetExchangePeeringSession.does_exist())
        # Make sure we can retrieve the session with its IP
        self.assertEqual(
            peering_session1,
            InternetExchangePeeringSession.does_exist(ip_address="192.168.1.1"),
        )
        # Make sure it returns None when using a field that the two sessions
        # have in common
        self.assertIsNone(
            InternetExchangePeeringSession.does_exist(
                internet_exchange=internet_exchange0
            )
        )

        # Create a new IX
        internet_exchange1 = InternetExchange.objects.create(name="Test1", slug="test1")

        # Make sure it returns None when there is no session
        self.assertIsNone(
            InternetExchangePeeringSession.does_exist(
                internet_exchange=internet_exchange1
            )
        )

        # Create a new session with a already used IP in another OX
        peering_session2 = InternetExchangePeeringSession.objects.create(
            autonomous_system=autonomous_system0,
            internet_exchange=internet_exchange1,
            ip_address="2001:db8::1",
        )

        # Make sure that the session has been created
        self.assertIsNotNone(peering_session2)
        # Make sure we have None, because two sessions will be found
        self.assertIsNone(
            InternetExchangePeeringSession.does_exist(ip_address="2001:db8::1")
        )
        # But if we narrow the search with the IX we must have the proper
        # session
        self.assertEqual(
            peering_session2,
            InternetExchangePeeringSession.does_exist(
                ip_address="2001:db8::1", internet_exchange=internet_exchange1
            ),
        )


class RouterTestCase(TestCase):
    def test_napalm_bgp_neighbors_to_peer_list(self):
        # Expected results
        expected = [0, 0, 1, 2, 3, 2, 2]

        napalm_dicts_list = [
            # If None or empty dict passed, returned value must be empty list
            None,
            {},
            # List size must match peers number including VRFs
            {"global": {"peers": {"192.168.0.1": {"remote_as": 64500}}}},
            {
                "global": {"peers": {"192.168.0.1": {"remote_as": 64500}}},
                "vrf": {"peers": {"192.168.1.1": {"remote_as": 64501}}},
            },
            {
                "global": {"peers": {"192.168.0.1": {"remote_as": 64500}}},
                "vrf0": {"peers": {"192.168.1.1": {"remote_as": 64501}}},
                "vrf1": {"peers": {"192.168.2.1": {"remote_as": 64502}}},
            },
            # If peer does not have remote_as field, it must be ignored
            {
                "global": {"peers": {"192.168.0.1": {"remote_as": 64500}}},
                "vrf0": {"peers": {"192.168.1.1": {"remote_as": 64501}}},
                "vrf1": {"peers": {"192.168.2.1": {"not_valid": 64502}}},
            },
            # If an IP address appears more than one time, only the first
            # occurence  must be retained
            {
                "global": {"peers": {"192.168.0.1": {"remote_as": 64500}}},
                "vrf0": {"peers": {"192.168.1.1": {"remote_as": 64501}}},
                "vrf1": {"peers": {"192.168.1.1": {"remote_as": 64502}}},
            },
        ]

        # Create a router
        router = Router.objects.create(
            name="test", hostname="test.example.com", platform=PLATFORM_JUNOS
        )

        # Run test cases
        for i in range(len(expected)):
            self.assertEqual(
                expected[i],
                len(router._napalm_bgp_neighbors_to_peer_list(napalm_dicts_list[i])),
            )


class RoutingPolicyTestCase(TestCase):
    def test_create(self):
        routing_policy_list = [
            {"name": "Test1", "slug": "test1", "type": None},
            {"name": "Test2", "slug": "test2", "type": ROUTING_POLICY_TYPE_EXPORT},
        ]

        for details in routing_policy_list:
            if details["type"]:
                routing_policy = RoutingPolicy.objects.create(
                    name=details["name"], slug=details["slug"], type=details["type"]
                )
            else:
                routing_policy = RoutingPolicy.objects.create(
                    name=details["name"], slug=details["slug"]
                )

            self.assertIsNotNone(routing_policy)
            self.assertEqual(details["name"], routing_policy.name)
            self.assertEqual(details["slug"], routing_policy.slug)
            self.assertEqual(
                details["type"] or ROUTING_POLICY_TYPE_IMPORT, routing_policy.type
            )

    def test_get_type_html(self):
        expected = [
            '<span class="badge badge-info">'
            '<i class="fas fa-arrow-circle-up"></i> Export</span>',
            '<span class="badge badge-info">'
            '<i class="fas fa-arrow-circle-down"></i> Import</span>',
            '<span class="badge badge-secondary">'
            '<i class="fas fa-ban"></i> Unknown</span>',
        ]
        routing_policy_types = [
            ROUTING_POLICY_TYPE_EXPORT,
            ROUTING_POLICY_TYPE_IMPORT,
            "unknown",
        ]

        for i in range(len(routing_policy_types)):
            self.assertEqual(
                expected[i],
                RoutingPolicy.objects.create(
                    name="test{}".format(i),
                    slug="test{}".format(i),
                    type=routing_policy_types[i],
                ).get_type_html(),
            )
