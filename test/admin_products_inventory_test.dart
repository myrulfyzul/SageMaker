import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/features/admin/inventory/data/inventory_validation.dart';
import 'package:sagemaker_flutter/features/admin/inventory/ui/inventory_screen.dart';
import 'package:sagemaker_flutter/features/admin/products/data/admin_product_validation.dart';
import 'package:sagemaker_flutter/features/admin/products/state/admin_products_provider.dart';
import 'package:sagemaker_flutter/features/admin/products/ui/admin_product_form_screen.dart';
import 'package:sagemaker_flutter/features/admin/products/ui/admin_products_screen.dart';

http.Response _json(int s, Object b) => http.Response(jsonEncode(b), s,
    headers: {'content-type': 'application/json'});

Map<String, Object?> _product(int id, {bool active = true}) => {
      'id': id,
      'name': 'Pouch $id',
      'description': 'd',
      'category': {'id': 1, 'name': 'Bags', 'slug': 'bags'},
      'priceSen': 2500,
      'isActive': active,
      'stock': {'quantity': 7, 'lowStockThreshold': 2},
      'images': <Object>[],
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
    test('price parses ringgit to sen and enforces range', () {
      expect(parsePriceSen('12.5'), 1250);
      expect(parsePriceSen('12'), 1200);
      expect(parsePriceSen('1.234'), isNull);
      expect(validatePriceRm('0'), isNotNull);
      expect(validatePriceRm('0.01'), isNull);
      expect(validatePriceRm('1000000'), isNotNull);
    });

    test('name, stock, threshold and image rules', () {
      expect(validateProductName(' '), isNotNull);
      expect(validateProductName('a' * 201), isNotNull);
      expect(validateStock('-1'), isNotNull);
      expect(validateStock('999999'), isNull);
      expect(validateThreshold('1000000'), isNotNull);
      expect(validateImage('a.PNG', 10), isNull);
      expect(validateImage('a.gif', 10), isNotNull);
      expect(validateImage('a.jpg', maxImageBytes + 1), isNotNull);
    });

    test('delta and reason rules', () {
      expect(validateDelta('0'), isNotNull);
      expect(validateDelta('1.5'), isNotNull);
      expect(validateDelta('-3'), isNull);
      expect(validateDelta('+3'), isNull);
      expect(validateDelta('1000000000'), isNotNull);
      expect(validateReason(''), isNotNull);
      expect(validateReason('a' * 256), isNotNull);
      expect(validateInventoryThreshold('-1'), isNotNull);
    });
  });

  testWidgets('products list shows items and searches by name', (tester) async {
    final queries = <String?>[];
    await _pump(tester, const AdminProductsScreen(), (r) async {
      if (r.url.path == '/api/staff/products') {
        queries.add(r.url.queryParameters['q']);
        return _json(200, {
          'items': [_product(1), _product(2, active: false)],
          'total': 2
        });
      }
      return _json(404, {});
    });
    expect(find.text('Pouch 1'), findsOneWidget);
    expect(find.textContaining('Inactive'), findsOneWidget);
    await tester.enterText(find.byType(TextField), 'pou');
    await tester.testTextInput.receiveAction(TextInputAction.search);
    await tester.pumpAndSettle();
    expect(queries.last, 'pou');
  });

  testWidgets('delete 409 recommends deactivation', (tester) async {
    var patched = false;
    await _pump(tester, const AdminProductsScreen(), (r) async {
      if (r.method == 'DELETE') {
        return _json(409, {
          'error': {'code': 'product_in_orders', 'message': 'in orders'}
        });
      }
      if (r.method == 'PATCH') {
        patched = true;
        return _json(200, _product(1, active: false));
      }
      return _json(200, {
        'items': [_product(1)],
        'total': 1
      });
    });
    await tester.tap(find.byTooltip('Delete Pouch 1'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete'));
    await tester.pumpAndSettle();
    expect(find.textContaining('Deactivate it instead'), findsOneWidget);
    await tester.tap(find.text('Deactivate'));
    await tester.pumpAndSettle();
    expect(patched, isTrue);
  });

  testWidgets('rejected create keeps values and shows the reason',
      (tester) async {
    await _pump(tester, const AdminProductFormScreen(), (r) async {
      if (r.url.path == '/api/categories') {
        return _json(200, [
          {'id': 1, 'slug': 'bags', 'name': 'Bags'}
        ]);
      }
      if (r.method == 'POST') {
        return _json(422, {
          'error': {
            'code': 'validation_error',
            'message': 'Invalid product',
            'details': [
              {'field': 'name', 'reason': 'name already used'}
            ]
          }
        });
      }
      return _json(404, {});
    });
    await tester.enterText(find.widgetWithText(TextFormField, 'Name'), 'Tote');
    await tester.enterText(find.widgetWithText(TextFormField, 'Price (RM)'), '9.90');
    await tester.enterText(find.widgetWithText(TextFormField, 'Stock'), '4');
    await tester.tap(find.byType(DropdownButtonFormField<int>));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Bags').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Create product'));
    await tester.pumpAndSettle();
    expect(find.text('name already used'), findsOneWidget);
    expect(find.text('Tote'), findsOneWidget);
    expect(find.text('New product'), findsOneWidget);
  });

  testWidgets('image picker rejects unsupported type', (tester) async {
    await _pump(tester, const AdminProductFormScreen(), (r) async {
      return _json(200, <Object>[]);
    }, extra: [
      productImagePickerProvider.overrideWithValue(() async =>
          PickedProductImage('x.gif', Uint8List.fromList([1, 2]))),
    ]);
    await tester.ensureVisible(find.text('Add image'));
    await tester.tap(find.text('Add image'));
    await tester.pumpAndSettle();
    expect(find.text('Use a PNG, JPEG or WebP image'), findsOneWidget);
  });

  testWidgets('inventory shows low-stock alert with count and adjusts',
      (tester) async {
    Map<String, Object?>? adjustBody;
    await _pump(tester, const InventoryScreen(), (r) async {
      if (r.method == 'POST') {
        adjustBody = jsonDecode(r.body) as Map<String, Object?>;
        return _json(409, {
          'error': {'code': 'insufficient_stock', 'message': 'no'}
        });
      }
      if (r.url.path.endsWith('/adjustments')) {
        return _json(200, {'items': <Object>[], 'total': 0});
      }
      return _json(200, {
        'items': [
          {'productId': 1, 'name': 'Pouch', 'quantity': 1, 'lowStockThreshold': 3, 'lowStock': true},
          {'productId': 2, 'name': 'Tote', 'quantity': 50, 'lowStockThreshold': 3, 'lowStock': false},
        ],
        'total': 2
      });
    });
    expect(find.text('Low stock: 1'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('stock-1')));
    await tester.pumpAndSettle();
    expect(find.text('No adjustments yet.'), findsOneWidget);
    await tester.enterText(
        find.widgetWithText(TextFormField, 'Change (for example 5 or -3)'), '-5');
    await tester.enterText(find.widgetWithText(TextFormField, 'Reason'), 'damaged');
    await tester.tap(find.text('Adjust stock'));
    await tester.pumpAndSettle();
    expect(adjustBody, {'delta': -5, 'reason': 'damaged'});
    expect(find.textContaining('Insufficient stock'), findsOneWidget);
  });
}
