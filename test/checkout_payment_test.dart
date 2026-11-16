import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/app/theme.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/features/auth/data/auth_user.dart';
import 'package:sagemaker_flutter/features/auth/state/session_provider.dart';
import 'package:sagemaker_flutter/features/checkout/data/checkout_models.dart';
import 'package:sagemaker_flutter/features/checkout/state/checkout_flow.dart';
import 'package:sagemaker_flutter/features/checkout/ui/checkout_screen.dart';
import 'package:sagemaker_flutter/features/payment/ui/confirmation_screen.dart';
import 'package:sagemaker_flutter/features/payment/data/malaysia_payments.dart';
import 'package:sagemaker_flutter/features/payment/ui/payment_chooser.dart';
import 'package:sagemaker_flutter/features/payment/ui/payment_gateway_screen.dart';

class _FakeSession extends SessionNotifier {
  @override
  SessionState build() => const SessionSignedIn(
      AuthUser(id: 1, name: 'C', email: 'c@x.my', role: AppRole.customer));
}

http.Response _json(int s, Object b) => http.Response(jsonEncode(b), s,
    headers: {'content-type': 'application/json'});

const _cart = {
  'lines': [
    {
      'id': 1,
      'productId': 'pouch',
      'name': 'Pouch',
      'variationLabel': null,
      'quantity': 2,
      'unitPriceSen': 2500,
      'lineTotalSen': 5000,
      'available': true,
    }
  ],
  'subtotalSen': 5000,
  'deliveryFeeSen': 800,
  'grandTotalSen': 5800,
};

Map<String, Object?> _order(String payment, String status) => {
      'id': 'SM-ABC1234567',
      'status': status,
      'paymentStatus': payment,
      'paymentMethod': 'card',
      'totalSen': 5800,
      'lines': [
        {'name': 'Pouch', 'quantity': 2, 'lineTotalSen': 5000}
      ],
    };

const _goodDelivery = DeliveryForm(
  name: 'Aisyah Rahman',
  phone: '012-345 6789',
  email: 'a@example.my',
  address: '12 Jalan Contoh, Taman Demo',
  postcode: '50000',
  state: 'Selangor',
);

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
  group('delivery validation (Req 12.3)', () {
    test('valid form has no errors', () {
      expect(validateDelivery(_goodDelivery), isEmpty);
    });

    test('each invalid field gets its own message', () {
      final errors = validateDelivery(const DeliveryForm(
          name: 'A',
          phone: '123',
          email: 'nope',
          address: 'short',
          postcode: '123',
          state: 'Atlantis'));
      expect(errors.keys.toSet(),
          {'name', 'phone', 'email', 'address', 'postcode', 'state'});
    });

    test('notes over 500 characters are rejected', () {
      expect(validateDelivery(_goodDelivery.copyWith(notes: 'x' * 501)).keys,
          ['notes']);
    });

    test('idempotency keys are 10 to 80 characters and unique', () {
      final keys = {for (var i = 0; i < 50; i++) newIdempotencyKey()};
      expect(keys.length, 50);
      for (final k in keys) {
        expect(k.length, inInclusiveRange(10, 80));
      }
    });
  });

  group('checkout flow', () {
    test('blocked delivery keeps values and stays on the step', () {
      final (c, _) = _container((_) async => _json(200, {}));
      final n = c.read(checkoutFlowProvider.notifier);
      n.goTo(1);
      n.updateDelivery(_goodDelivery.copyWith(postcode: '12'));
      expect(n.continueFromDelivery(), isFalse);
      final s = c.read(checkoutFlowProvider);
      expect(s.step, 1);
      expect(s.errors.keys, ['postcode']);
      expect(s.delivery.name, 'Aisyah Rahman');
    });

    test(
        'network error keeps form and key, retry reuses the key and sends no card data',
        () async {
      var fail = true;
      final (c, calls) = _container((r) async {
        if (r.url.path == '/api/checkout') {
          if (fail) {
            return _json(500, {
              'error': {'message': 'x'}
            });
          }
          return _json(201, _order('paid', 'placed'));
        }
        return _json(200, {});
      });
      final n = c.read(checkoutFlowProvider.notifier);
      n.updateDelivery(_goodDelivery);
      n.chooseMethod('card');
      n.chooseOutcome('success');

      expect(await n.submit(), isNull);
      var s = c.read(checkoutFlowProvider);
      expect(s.error, couldNotProcessMessage);
      expect(s.delivery.email, 'a@example.my');
      final key = s.idempotencyKey;
      expect(key, isNotNull);

      fail = false;
      expect(await n.submit(), 'SM-ABC1234567');
      s = c.read(checkoutFlowProvider);
      expect(s.idempotencyKey, key);

      final bodies = [
        for (final r in calls.where((r) => r.url.path == '/api/checkout'))
          jsonDecode(r.body) as Map<String, dynamic>
      ];
      expect(bodies.length, 2);
      expect(bodies[0]['idempotencyKey'], bodies[1]['idempotencyKey']);
      expect(bodies[0].keys.toSet(),
          {'idempotencyKey', 'delivery', 'method', 'outcome'});
      expect(jsonEncode(bodies), isNot(contains('card_number')));
    });

    test('server field errors return to the delivery step', () async {
      final (c, _) = _container((r) async => _json(422, {
            'error': {
              'code': 'validation_error',
              'message': 'bad',
              'details': [
                {
                  'field': 'delivery.phone',
                  'reason': 'must be a valid Malaysian phone number'
                }
              ]
            }
          }));
      final n = c.read(checkoutFlowProvider.notifier);
      n.updateDelivery(_goodDelivery);
      n.chooseMethod('cod');
      n.goTo(3);
      expect(await n.submit(), isNull);
      final s = c.read(checkoutFlowProvider);
      expect(s.step, 1);
      expect(s.errors['phone'], contains('Malaysian'));
    });

    test('409 lists the short items', () async {
      final (c, _) = _container((r) async => _json(409, {
            'error': {
              'code': 'insufficient_stock',
              'message': 'short',
              'details': [
                {'productId': 'pouch', 'requested': 2, 'available': 1}
              ]
            }
          }));
      final n = c.read(checkoutFlowProvider.notifier);
      n.updateDelivery(_goodDelivery);
      n.chooseMethod('cod');
      await n.submit();
      expect(c.read(checkoutFlowProvider).shortages.single.available, 1);
    });
  });

  group('screens', () {
    Widget host(ProviderContainer c, Widget child) => UncontrolledProviderScope(
        container: c, child: MaterialApp(theme: buildAppTheme(), home: child));

    testWidgets('checkout walks four steps and shows inline errors',
        (tester) async {
      final (c, _) = _container((r) async {
        if (r.url.path == '/api/cart') return _json(200, _cart);
        return _json(200, <Object>[]);
      });
      await tester.pumpWidget(host(c, const CheckoutScreen()));
      await tester.pumpAndSettle();
      expect(find.text('Step 1 of 4: Cart review'), findsOneWidget);

      await tester.tap(find.byKey(const Key('stepNext')));
      await tester.pumpAndSettle();
      expect(find.text('Step 2 of 4: Delivery details'), findsOneWidget);

      await tester.tap(find.byKey(const Key('stepNext')));
      await tester.pumpAndSettle();
      expect(find.text('Step 2 of 4: Delivery details'), findsOneWidget);
      expect(find.text('Name must be 2 to 100 characters'), findsOneWidget);

      c.read(checkoutFlowProvider.notifier).updateDelivery(_goodDelivery);
      await tester.tap(find.byKey(const Key('stepNext')));
      await tester.pumpAndSettle();
      expect(find.text('Step 3 of 4: Payment method'), findsOneWidget);
      expect(find.text('How would you like to pay?'), findsOneWidget);
    });

    testWidgets('FPX shows the bank list; picking a bank reports it',
        (tester) async {
      PaymentChannel? channel;
      String? provider;
      await tester.pumpWidget(MaterialApp(
        theme: buildAppTheme(),
        home: StatefulBuilder(
          builder: (context, set) => Scaffold(
            body: SingleChildScrollView(
              child: PaymentChooser(
                channel: channel,
                providerId: provider,
                onChanged: (c, p) => set(() {
                  channel = c;
                  provider = p;
                }),
              ),
            ),
          ),
        ),
      ));
      expect(find.byKey(const Key('provider-maybank2u')), findsNothing);
      await tester.tap(find.byKey(const Key('channel-fpx')));
      await tester.pumpAndSettle();
      expect(channel, PaymentChannel.fpx);
      expect(find.byKey(const Key('provider-maybank2u')), findsOneWidget);
      await tester.ensureVisible(find.byKey(const Key('provider-maybank2u')));
      await tester.tap(find.byKey(const Key('provider-maybank2u')));
      await tester.pumpAndSettle();
      expect(provider, 'maybank2u');
      await tester.ensureVisible(find.byKey(const Key('channel-cod')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('channel-cod')));
      await tester.pumpAndSettle();
      expect(channel, PaymentChannel.cod);
      expect(provider, isNull);
      expect(find.byKey(const Key('provider-maybank2u')), findsNothing);
    });

    test('FPX needs a bank before review; COD does not', () {
      final (c, _) = _container((r) async => _json(200, {}));
      final n = c.read(checkoutFlowProvider.notifier);
      n.chooseChannel(PaymentChannel.fpx);
      expect(n.continueFromPayment(), isFalse);
      expect(c.read(checkoutFlowProvider).error, 'Choose your bank.');
      n.chooseChannel(PaymentChannel.fpx, providerId: 'cimb');
      expect(n.continueFromPayment(), isTrue);
      n.chooseChannel(PaymentChannel.cod);
      expect(c.read(checkoutFlowProvider).providerId, isNull);
      expect(c.read(checkoutFlowProvider).paymentChosen, isTrue);
    });

    test('card number and expiry checks', () {
      expect(luhnValid('4111111111111111'), isTrue);
      expect(luhnValid('4111111111111112'), isFalse);
      expect(cardBrand('4111'), 'VISA');
      expect(cardBrand('5500'), 'Mastercard');
      final now = DateTime(2026, 11, 1);
      expect(expiryValid('11/26', now), isTrue);
      expect(expiryValid('10/26', now), isFalse);
      expect(expiryValid('13/30', now), isFalse);
    });

    testWidgets('e-wallet PIN 000000 is declined by the gateway',
        (tester) async {
      String? result;
      await tester.pumpWidget(MaterialApp(
        theme: buildAppTheme(),
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: TextButton(
                onPressed: () async => result = await openPaymentGateway(
                    context,
                    channel: PaymentChannel.ewallet,
                    providerId: 'tng',
                    amountSen: 4600),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byKey(const Key('pin-0')));
      await tester.pumpAndSettle();
      for (var i = 0; i < 6; i++) {
        await tester.tap(find.byKey(const Key('pin-0')));
        await tester.pump();
      }
      // PIN complete -> _finish: 250 ms, then 1400 ms processing.
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 1500));
      expect(find.text('Payment declined'), findsOneWidget);
      // 1100 ms result hold, then the route pops with the outcome.
      await tester.pump(const Duration(milliseconds: 1200));
      await tester.pumpAndSettle();
      expect(result, 'failed');
    });
    Future<void> pumpConfirmation(
        WidgetTester tester, String payment, String status) async {
      final (c, _) =
          _container((r) async => _json(200, _order(payment, status)));
      await tester.pumpWidget(
          host(c, const ConfirmationScreen(orderId: 'SM-ABC1234567')));
      await tester.pumpAndSettle();
    }

    testWidgets('confirmation (paid): track order, no retry', (tester) async {
      await pumpConfirmation(tester, 'paid', 'placed');
      expect(find.text('Payment successful'), findsOneWidget);
      expect(find.text('Track order'), findsOneWidget);
      expect(find.text('Retry payment'), findsNothing);
      expect(find.text('Return to shop'), findsOneWidget);
    });

    testWidgets('confirmation (failed): retry offered', (tester) async {
      await pumpConfirmation(tester, 'failed', 'payment_failed');
      expect(find.text('Payment failed'), findsOneWidget);
      expect(find.text('Retry payment'), findsOneWidget);
      expect(find.text('Return to shop'), findsOneWidget);
    });

    testWidgets('confirmation (cancelled): no retry', (tester) async {
      await pumpConfirmation(tester, 'cancelled', 'cancelled');
      expect(find.text('Payment cancelled'), findsOneWidget);
      expect(find.text('Retry payment'), findsNothing);
    });
  });
}
