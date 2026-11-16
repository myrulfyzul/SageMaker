import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/features/custom_orders/data/custom_order_validation.dart';
import 'package:sagemaker_flutter/features/custom_orders/data/custom_orders_repository.dart';
import 'package:sagemaker_flutter/features/custom_orders/state/custom_orders_provider.dart';
import 'package:sagemaker_flutter/features/custom_orders/ui/custom_order_detail_screen.dart';
import 'package:sagemaker_flutter/features/custom_orders/ui/custom_order_form_screen.dart';
import 'package:sagemaker_flutter/features/custom_orders/ui/custom_orders_screen.dart';

http.Response _json(int s, Object b) => http.Response(jsonEncode(b), s,
    headers: {'content-type': 'application/json'});

Map<String, Object?> _order(int id,
        {String status = 'submitted',
        int? price,
        String? reason,
        List<String> images = const []}) =>
    {
      'id': id,
      'productType': 'Tote bag',
      'description': 'A handwoven tote bag',
      'quantity': 3,
      'preferredDate': '2030-01-02',
      'status': status,
      'estimatedPriceSen': price,
      'rejectReason': reason,
      'imageUrls': images,
      'createdAt': '2025-06-01T03:04:05Z',
    };

Future<void> _pump(WidgetTester tester, Widget screen,
    Future<http.Response> Function(http.Request r) handler,
    {List<Override> extra = const []}) async {
  tester.view.physicalSize = const Size(800, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(ProviderScope(
    overrides: [
      apiClientProvider.overrideWithValue(ApiClient(
          baseUrl: 'http://t', client: MockClient(handler), token: 't')),
      ...extra,
    ],
    child: MaterialApp(home: screen),
  ));
  await tester.pumpAndSettle();
}

void main() {
  group('validation', () {
    test('quantity must be a whole number 1..500', () {
      expect(validateQuantity('1'), isNull);
      expect(validateQuantity('500'), isNull);
      for (final bad in ['0', '501', '1.5', '', 'x', '-1']) {
        expect(validateQuantity(bad), isNotNull, reason: bad);
      }
    });

    test('description and product type lengths', () {
      expect(validateDescription('too short'), isNotNull);
      expect(validateDescription('long enough text'), isNull);
      expect(validateProductType('  '), isNotNull);
      expect(validateProductType('a' * 101), isNotNull);
    });

    test('preferred date is today or later', () {
      final today = DateTime(2030, 5, 10, 15);
      expect(
          validatePreferredDate(DateTime(2030, 5, 10), today: today), isNull);
      expect(
          validatePreferredDate(DateTime(2030, 5, 9), today: today), isNotNull);
      expect(validatePreferredDate(null, today: today), isNotNull);
    });

    test('image type and size', () {
      expect(validateImage('a.PNG', 100), isNull);
      expect(validateImage('a.webp', maxCustomOrderImageBytes), isNull);
      expect(validateImage('a.gif', 100), isNotNull);
      expect(validateImage('a.jpg', maxCustomOrderImageBytes + 1), isNotNull);
      expect(validateImage('noext', 1), isNotNull);
    });
  });

  testWidgets('list shows own orders with status and estimate', (tester) async {
    await _pump(tester, const CustomOrdersScreen(), (r) async {
      expect(r.url.path, '/api/custom-orders');
      return _json(200, {
        'items': [_order(2, status: 'accepted', price: 12000), _order(1)],
        'total': 2,
        'limit': 20,
        'offset': 0,
      });
    });
    expect(find.text('Tote bag'), findsNWidgets(2));
    expect(find.text('Accepted'), findsOneWidget);
    expect(find.text('Submitted'), findsOneWidget);
    expect(find.textContaining('RM 120.00'), findsOneWidget);
  });

  testWidgets('list shows empty state and error with retry', (tester) async {
    await _pump(tester, const CustomOrdersScreen(), (r) async {
      return _json(200, {'items': [], 'total': 0, 'limit': 20, 'offset': 0});
    });
    expect(find.text('You have no custom orders yet.'), findsOneWidget);

    await _pump(
        tester,
        const CustomOrdersScreen(),
        (r) async => _json(500, {
              'error': {'code': 'x', 'message': 'boom'}
            }));
    expect(find.text('Retry'), findsOneWidget);
  });

  testWidgets('detail shows quoted price and rejection reason', (tester) async {
    await _pump(tester, const CustomOrderDetailScreen(orderId: 4),
        (r) async => _json(200, _order(4, status: 'accepted', price: 5050)));
    expect(find.text('Quoted price: RM 50.50'), findsOneWidget);

    await _pump(
        tester,
        const CustomOrderDetailScreen(orderId: 5),
        (r) async => _json(
            200, _order(5, status: 'rejected', reason: 'Cannot make this')));
    expect(find.textContaining('Cannot make this'), findsOneWidget);
  });

  testWidgets('detail loads images with the auth header', (tester) async {
    await _pump(tester, const CustomOrderDetailScreen(orderId: 6),
        (r) async => _json(200, _order(6, images: ['/api/media/a.png'])));
    final img = tester.widget<Image>(find.byType(Image));
    final provider = img.image as NetworkImage;
    expect(provider.url, 'http://t/api/media/a.png');
    expect(provider.headers, {'Authorization': 'Bearer t'});
  });

  testWidgets('form blocks invalid input and rejects bad images',
      (tester) async {
    var posts = 0;
    await _pump(tester, const CustomOrderFormScreen(), (r) async {
      posts++;
      return _json(201, _order(9));
    }, extra: [
      imagePickerProvider.overrideWithValue((limit) async => [
            PickedImage('x.gif', Uint8List(4)),
            PickedImage('ok.png', Uint8List(4)),
          ]),
    ]);
    await tester.tap(find.text('Add images'));
    await tester.pumpAndSettle();
    expect(find.textContaining('only PNG, JPEG or WebP'), findsOneWidget);
    expect(find.text('ok.png'), findsOneWidget);

    await tester.ensureVisible(find.text('Submit request'));
    await tester.tap(find.text('Submit request'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Product type must be'), findsOneWidget);
    expect(find.text('Choose a preferred date'), findsOneWidget);
    expect(posts, 0);
  });

  test('repository sends multipart fields and files', () async {
    late http.BaseRequest seen;
    final client = ApiClient(
        baseUrl: 'http://t',
        token: 't',
        client: MockClient.streaming((req, body) async {
          seen = req;
          final bytes = await body.toBytes();
          final text = latin1.decode(bytes);
          expect(text, contains('name="productType"'));
          expect(text, contains('name="quantity"'));
          expect(text, contains('filename="a.png"'));
          return http.StreamedResponse(
              Stream.value(utf8.encode(jsonEncode(_order(1)))), 201,
              headers: {'content-type': 'application/json'});
        }));
    final created = await CustomOrdersRepository(client).create(
      productType: 'Tote',
      description: 'A handwoven tote bag',
      quantity: 3,
      preferredDate: '2030-01-02',
      images: [
        PickedImage('a.png', Uint8List.fromList([1, 2, 3]))
      ],
    );
    expect(created.id, 1);
    expect(seen.headers['Authorization'], 'Bearer t');
  });
}
