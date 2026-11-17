import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/app/theme.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/features/auth/data/auth_user.dart';
import 'package:sagemaker_flutter/features/auth/state/session_provider.dart';
import 'package:sagemaker_flutter/features/checkout/data/checkout_models.dart';
import 'package:sagemaker_flutter/features/checkout/state/checkout_flow.dart';
import 'package:sagemaker_flutter/features/payment/data/malaysia_payments.dart';
import 'package:sagemaker_flutter/features/payment/data/payment_gateway.dart';
import 'package:sagemaker_flutter/features/payment/ui/payment_chooser.dart';
import 'package:sagemaker_flutter/features/payment/ui/payment_wait_screen.dart';

class _FakeSession extends SessionNotifier {
  @override
  SessionState build() => const SessionSignedIn(
      AuthUser(id: 1, name: 'C', email: 'c@x.my', role: AppRole.customer));
}

http.Response _json(int s, Object b) => http.Response(jsonEncode(b), s,
    headers: {'content-type': 'application/json'});

const _hosted = PaymentConfig(
    gateway: 'stripe',
    methods: ['fpx', 'ewallet', 'card', 'cod'],
    ewalletProvider: 'grabpay');

const _delivery = DeliveryForm(
  name: 'Aisyah Rahman',
  phone: '012-345 6789',
  email: 'a@example.my',
  address: '12 Jalan Contoh, Taman Indah',
  postcode: '50000',
  state: 'Selangor',
);

Map<String, Object?> _payment(String status,
        {String? orderId, String? message, String? url}) =>
    {
      'id': 'PS-1',
      'status': status,
      'orderId': orderId,
      'method': 'fpx',
      'provider': null,
      'amountSen': 5800,
      'checkoutUrl': url,
      'message': message,
    };

(ProviderContainer, List<http.Request>) _container(
    Future<http.Response> Function(http.Request) handler) {
  final calls = <http.Request>[];
  final c = ProviderContainer(overrides: [
    sessionProvider.overrideWith(_FakeSession.new),
    apiClientProvider.overrideWithValue(ApiClient(
      baseUrl: 'http://t',
      token: 'tok',
      client: MockClient((r) {
        calls.add(r);
        return handler(r);
      }),
    )),
  ]);
  addTearDown(c.dispose);
  return (c, calls);
}

void main() {
  group('config and models', () {
    test('config tells the hosted gateway from the prototype', () {
      final c = PaymentConfig.fromJson({
        'gateway': 'stripe',
        'sandbox': true,
        'methods': ['fpx', 'ewallet', 'card', 'cod'],
        'ewalletProvider': 'grabpay',
      });
      expect(c.isHosted, isTrue);
      expect(c.ewalletProvider, 'grabpay');
      expect(
          PaymentConfig.fromJson({'gateway': 'prototype'}).isHosted, isFalse);
      expect(const PaymentConfig().isHosted, isFalse);
    });

    test('config falls back to the prototype when the server cannot say',
        () async {
      final (c, _) = _container((r) async => _json(500, {'error': {}}));
      expect((await c.read(paymentConfigProvider.future)).isHosted, isFalse);
    });

    test('a payment is paid only when it has an order', () {
      expect(GatewayPayment.fromJson(_payment('pending')).isPending, isTrue);
      expect(GatewayPayment.fromJson(_payment('paid', orderId: 'SM-1')).isPaid,
          isTrue);
      expect(GatewayPayment.fromJson(_payment('paid')).isPaid, isFalse);
    });

    test('provider id: the chosen bank or wallet, duitnow for QR, none else',
        () {
      expect(PaymentChannel.fpx.providerFor('cimb'), 'cimb');
      expect(PaymentChannel.ewallet.providerFor('grabpay'), 'grabpay');
      expect(PaymentChannel.duitnow.providerFor(null), 'duitnow');
      expect(PaymentChannel.card.providerFor('cimb'), isNull);
      expect(PaymentChannel.cod.providerFor('cimb'), isNull);
    });
  });

  group('checkout flow with the hosted gateway', () {
    test('no bank is needed in the app; the request carries no outcome',
        () async {
      final (c, calls) = _container((r) async {
        if (r.url.path == '/api/payments/sessions') {
          return _json(201, _payment('pending', url: 'https://pay.test/x'));
        }
        return _json(200, {});
      });
      final n = c.read(checkoutFlowProvider.notifier);
      n.useGateway(true);
      n.updateDelivery(_delivery);
      n.chooseChannel(PaymentChannel.fpx);
      expect(n.continueFromPayment(), isTrue);

      final payment = await n.startGatewayPayment();
      expect(payment!.checkoutUrl, 'https://pay.test/x');
      final req =
          calls.singleWhere((r) => r.url.path == '/api/payments/sessions');
      final body = jsonDecode(req.body) as Map<String, dynamic>;
      expect(body['method'], 'fpx');
      expect(body.containsKey('outcome'), isFalse);
      expect(body['idempotencyKey'], isNotNull);
      expect(jsonEncode(body), isNot(contains('card_number')));
      expect(c.read(checkoutFlowProvider).submitting, isFalse);
    });

    test('without the gateway a bank is still required', () {
      final (c, _) = _container((r) async => _json(200, {}));
      final n = c.read(checkoutFlowProvider.notifier);
      n.chooseChannel(PaymentChannel.fpx);
      expect(n.continueFromPayment(), isFalse);
    });

    test('e-wallet sends grabpay as the provider', () async {
      final (c, calls) =
          _container((r) async => _json(201, _payment('pending')));
      final n = c.read(checkoutFlowProvider.notifier);
      n.useGateway(true);
      n.updateDelivery(_delivery);
      n.chooseChannel(PaymentChannel.ewallet, providerId: 'grabpay');
      await n.startGatewayPayment();
      final body = jsonDecode(calls.last.body) as Map<String, dynamic>;
      expect(body['method'], 'ewallet');
      expect(body['provider'], 'grabpay');
    });

    test('the same key is reused until the attempt is reset', () async {
      final (c, calls) =
          _container((r) async => _json(201, _payment('pending')));
      final n = c.read(checkoutFlowProvider.notifier);
      n.useGateway(true);
      n.updateDelivery(_delivery);
      n.chooseChannel(PaymentChannel.card);
      await n.startGatewayPayment();
      await n.startGatewayPayment();
      n.resetAttempt();
      await n.startGatewayPayment();
      final keys = [
        for (final r in calls) (jsonDecode(r.body) as Map)['idempotencyKey']
      ];
      expect(keys[0], keys[1]);
      expect(keys[2], isNot(keys[0]));
    });

    test('invalid delivery stops before any request', () async {
      final (c, calls) =
          _container((r) async => _json(201, _payment('pending')));
      final n = c.read(checkoutFlowProvider.notifier);
      n.useGateway(true);
      n.chooseChannel(PaymentChannel.fpx);
      expect(await n.startGatewayPayment(), isNull);
      expect(calls, isEmpty);
      expect(c.read(checkoutFlowProvider).step, 1);
    });

    test('a refused start keeps the form and shows the server message',
        () async {
      final (c, _) = _container((r) async => _json(502, {
            'error': {
              'code': 'payment_gateway_error',
              'message': 'The payment gateway could not be reached.'
            }
          }));
      final n = c.read(checkoutFlowProvider.notifier);
      n.useGateway(true);
      n.updateDelivery(_delivery);
      n.chooseChannel(PaymentChannel.fpx);
      expect(await n.startGatewayPayment(), isNull);
      final s = c.read(checkoutFlowProvider);
      expect(s.delivery.email, 'a@example.my');
      expect(s.error, isNotNull);
      expect(s.submitting, isFalse);
    });
  });

  group('payment chooser with the hosted gateway', () {
    Future<void> pump(WidgetTester tester,
        {PaymentConfig? config,
        bool codOnly = false,
        void Function(PaymentChannel, String?)? onChanged,
        PaymentChannel? channel}) async {
      await tester.pumpWidget(MaterialApp(
        theme: buildAppTheme(),
        home: Scaffold(
          body: SingleChildScrollView(
            child: PaymentChooser(
              channel: channel,
              providerId: null,
              config: config,
              codOnly: codOnly,
              onChanged: onChanged ?? (_, __) {},
            ),
          ),
        ),
      ));
    }

    testWidgets('hides DuitNow QR and the in-app bank list; GrabPay only',
        (tester) async {
      PaymentChannel? picked;
      String? provider;
      await pump(tester, config: _hosted, channel: PaymentChannel.fpx,
          onChanged: (c, p) {
        picked = c;
        provider = p;
      });
      expect(find.byKey(const Key('channel-duitnow')), findsNothing);
      expect(find.byKey(const Key('provider-maybank2u')), findsNothing,
          reason: 'the gateway page lists the banks');
      expect(find.text('GrabPay'), findsOneWidget);
      expect(find.textContaining("Touch 'n Go"), findsNothing);
      expect(find.textContaining('sandbox'), findsOneWidget);

      await tester.tap(find.byKey(const Key('channel-ewallet')));
      expect(picked, PaymentChannel.ewallet);
      expect(provider, 'grabpay');
      await tester.tap(find.byKey(const Key('channel-fpx')));
      expect(picked, PaymentChannel.fpx);
      expect(provider, isNull);
    });

    testWidgets('FPX is hidden when the Stripe account has not switched it on',
        (tester) async {
      await pump(tester,
          config: const PaymentConfig(
              gateway: 'stripe',
              methods: ['ewallet', 'card', 'cod'],
              ewalletProvider: 'grabpay'));
      expect(find.byKey(const Key('channel-fpx')), findsNothing);
      expect(find.byKey(const Key('channel-ewallet')), findsOneWidget);
      expect(find.byKey(const Key('channel-card')), findsOneWidget);
      expect(find.byKey(const Key('channel-cod')), findsOneWidget);
    });

    testWidgets('the prototype keeps DuitNow QR and the bank list',
        (tester) async {
      await pump(tester, channel: PaymentChannel.fpx);
      expect(find.byKey(const Key('channel-duitnow')), findsOneWidget);
      expect(find.byKey(const Key('provider-maybank2u')), findsOneWidget);
    });

    testWidgets(
        'cash on delivery only, for orders that cannot be re-paid online',
        (tester) async {
      await pump(tester, config: _hosted, codOnly: true);
      expect(find.byKey(const Key('channel-cod')), findsOneWidget);
      expect(find.byKey(const Key('channel-fpx')), findsNothing);
      expect(find.byKey(const Key('channel-card')), findsNothing);
    });
  });

  group('payment wait screen', () {
    Future<List<String>> pumpWait(
      WidgetTester tester,
      List<Map<String, Object?>> statusReplies, {
      Future<http.Response> Function(http.Request)? onCancel,
    }) async {
      final paths = <String>[];
      var i = 0;
      final (c, _) = _container((r) async {
        paths.add('${r.method} ${r.url.path}');
        if (r.url.path.endsWith('/cancel')) {
          return onCancel != null
              ? onCancel(r)
              : _json(200,
                  _payment('cancelled', message: 'You cancelled the payment'));
        }
        final reply = statusReplies[
            i < statusReplies.length ? i : statusReplies.length - 1];
        i++;
        return _json(200, reply);
      });
      final router = GoRouter(initialLocation: '/payment/wait/PS-1', routes: [
        GoRoute(
          path: '/payment/wait/:paymentId',
          builder: (_, s) => PaymentWaitScreen(
            paymentId: s.pathParameters['paymentId']!,
            checkoutUrl: 'https://pay.test/x',
            pollInterval: const Duration(seconds: 1),
            autoOpen: false,
          ),
        ),
        GoRoute(
            path: '/confirmation/:orderId',
            builder: (_, s) => Scaffold(
                body: Text('confirmed ${s.pathParameters['orderId']}'))),
        GoRoute(
            path: '/checkout',
            builder: (_, __) => const Scaffold(body: Text('checkout'))),
      ]);
      addTearDown(router.dispose);
      await tester.pumpWidget(UncontrolledProviderScope(
        container: c,
        child: MaterialApp.router(theme: buildAppTheme(), routerConfig: router),
      ));
      return paths;
    }

    testWidgets('polls until the payment is paid, then opens the confirmation',
        (tester) async {
      final paths = await pumpWait(tester, [
        _payment('pending', url: 'https://pay.test/x'),
        _payment('paid', orderId: 'SM-PAID000001'),
      ]);
      expect(find.text('Waiting for your payment'), findsOneWidget);
      await tester.pump(const Duration(seconds: 1));
      await tester.pump();
      expect(find.text('Waiting for your payment'), findsOneWidget);
      await tester.pump(const Duration(seconds: 1));
      await tester.pumpAndSettle();
      expect(find.text('confirmed SM-PAID000001'), findsOneWidget);
      expect(
          paths.where((p) => p == 'GET /api/payments/sessions/PS-1').length, 2);
    });

    testWidgets('"check now" confirms without waiting for the timer',
        (tester) async {
      await pumpWait(tester, [_payment('paid', orderId: 'SM-NOW0000001')]);
      await tester.tap(find.byKey(const Key('wait-check')));
      await tester.pumpAndSettle();
      expect(find.text('confirmed SM-NOW0000001'), findsOneWidget);
    });

    testWidgets('cancel shows the result and returns to checkout',
        (tester) async {
      final paths = await pumpWait(tester, [_payment('pending')]);
      await tester.tap(find.byKey(const Key('wait-cancel')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('wait-result-title')), findsOneWidget);
      expect(find.text('Payment cancelled'), findsOneWidget);
      expect(find.text('You cancelled the payment'), findsOneWidget);
      expect(paths, contains('POST /api/payments/sessions/PS-1/cancel'));
      await tester.tap(find.byKey(const Key('wait-back')));
      await tester.pumpAndSettle();
      expect(find.text('checkout'), findsOneWidget);
    });

    testWidgets('a refund is explained, not shown as a success',
        (tester) async {
      await pumpWait(tester, [
        _payment('refunded',
            message:
                'Some items sold out while you were paying, so the payment was refunded')
      ]);
      await tester.tap(find.byKey(const Key('wait-check')));
      await tester.pumpAndSettle();
      expect(find.text('Payment refunded'), findsOneWidget);
      expect(find.textContaining('sold out'), findsOneWidget);
      expect(find.textContaining('confirmed'), findsNothing);
    });

    testWidgets('a network error keeps waiting and says so', (tester) async {
      final (c, _) =
          _container((r) async => throw http.ClientException('offline'));
      await tester.pumpWidget(UncontrolledProviderScope(
        container: c,
        child: MaterialApp(
          theme: buildAppTheme(),
          home: const PaymentWaitScreen(
              paymentId: 'PS-1', checkoutUrl: null, autoOpen: false),
        ),
      ));
      await tester.tap(find.byKey(const Key('wait-check')));
      await tester.pump();
      await tester.pump();
      expect(find.byKey(const Key('wait-check-failed')), findsOneWidget);
      expect(find.text('Waiting for your payment'), findsOneWidget);
      // Leave the screen so its polling timer is cancelled.
      await tester.pumpWidget(const SizedBox());
    });
  });
}
