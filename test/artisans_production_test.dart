import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_riverpod/misc.dart' show Override;
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/features/admin/artisans/data/artisan_validation.dart';
import 'package:sagemaker_flutter/features/admin/artisans/ui/artisans_screen.dart';
import 'package:sagemaker_flutter/features/admin/production/data/production_models.dart';
import 'package:sagemaker_flutter/features/admin/production/data/production_validation.dart';
import 'package:sagemaker_flutter/features/admin/production/state/production_provider.dart';
import 'package:sagemaker_flutter/features/admin/production/ui/production_screen.dart';
import 'package:sagemaker_flutter/features/auth/data/auth_user.dart';

http.Response _json(int s, Object b) => http.Response(jsonEncode(b), s,
    headers: {'content-type': 'application/json'});

Map<String, Object?> _job(int id,
        {String status = 'in_production',
        bool overdue = false,
        int? artisanId = 1}) =>
    {
      'id': id,
      'orderId': 'o$id',
      'productName': 'Batik $id',
      'quantity': 2,
      'status': status,
      'priority': 'normal',
      'artisanId': artisanId,
      'artisanName': artisanId == null ? null : 'Aminah',
      'deadline': '2099-01-01',
      'progressPercent': 40,
      'notes': '',
      'overdue': overdue,
      'progressHistory': <Object>[],
    };

Map<String, Object?> _artisan(int id, {String availability = 'available'}) => {
      'id': id,
      'name': 'Aminah',
      'specialisation': 'Batik',
      'availability': availability,
      'story': '',
      'isActive': true,
      'privateContact': {'phone': '0123456789', 'email': null, 'address': null},
      'assignedProducts': <Object>[],
      'openJobCount': 1,
      'completedJobCount': 0,
    };

Future<void> _pump(WidgetTester tester, Widget screen,
    Future<http.Response> Function(http.Request r) handler,
    {List<Override> extra = const []}) async {
  tester.view.physicalSize = const Size(900, 2400);
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
    test('artisan fields', () {
      expect(validateArtisanName(' '), isNotNull);
      expect(validateArtisanName('a' * 101), isNotNull);
      expect(validateSpecialisation('Batik'), isNull);
      expect(validateAvailability('gone'), isNotNull);
      expect(validateArtisanEmail(''), isNull);
      expect(validateArtisanEmail('nope'), isNotNull);
    });

    test('job quantity, deadline, progress', () {
      expect(validateJobQuantity('0'), isNotNull);
      expect(validateJobQuantity('999999'), isNull);
      expect(validateJobQuantity('1.5'), isNotNull);
      final today = DateTime(2025, 5, 10);
      expect(validateDeadline('2025-05-09', today: today), isNotNull);
      expect(validateDeadline('2025-05-10', today: today), isNull);
      expect(validateDeadline('2025-02-30', today: today), isNotNull);
      expect(validateProgressPercent('101'), isNotNull);
      expect(validateProgressPercent('-1'), isNotNull);
      expect(validateProgressPercent('100'), isNull);
    });

    test('status transitions follow the sequence', () {
      expect(nextStatuses('quality_checking'), ['completed', 'in_production']);
      expect(nextStatuses('ready_for_fulfilment'), isEmpty);
      expect(nextStatuses('order_confirmed'), ['production_assigned']);
    });
  });

  testWidgets('artisans list shows availability', (tester) async {
    await _pump(tester, const ArtisansScreen(), (r) async {
      return _json(200, {
        'items': [_artisan(1, availability: 'unavailable')],
        'total': 1
      });
    });
    expect(find.text('Aminah'), findsOneWidget);
    expect(find.text('Unavailable'), findsOneWidget);
  });

  testWidgets('unavailable save with open jobs shows warning', (tester) async {
    await _pump(tester, const ArtisansScreen(), (r) async {
      if (r.method == 'PUT') {
        return _json(200, {
          ..._artisan(1, availability: 'unavailable'),
          'warnings': [
            {'jobIds': [4, 9]}
          ],
        });
      }
      if (r.url.path == '/api/staff/artisans/1') return _json(200, _artisan(1));
      return _json(200, {
        'items': [_artisan(1)],
        'total': 1
      });
    });
    await tester.tap(find.text('Aminah'));
    await tester.pumpAndSettle();
    expect(find.text('0123456789'), findsOneWidget); // private contact: staff
    await tester.tap(find.byKey(const ValueKey('artisan-availability')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Unavailable').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Save'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('unavailable-warning')), findsOneWidget);
    expect(find.textContaining('#4, #9'), findsOneWidget);
  });

  testWidgets('production list flags overdue and board groups by status',
      (tester) async {
    await _pump(tester, const ProductionScreen(), (r) async {
      if (r.url.path == '/api/staff/artisans') {
        return _json(200, {'items': [_artisan(1)], 'total': 1});
      }
      return _json(200, {
        'items': [
          _job(1, overdue: true),
          _job(2, status: 'completed'),
        ],
        'total': 2
      });
    });
    expect(find.text('Overdue'), findsOneWidget);
    await tester.tap(find.byTooltip('Show board view'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('column-in_production')), findsOneWidget);
    expect(find.text('In production (1)'), findsOneWidget);
  });

  testWidgets('empty filtered result offers clear filters', (tester) async {
    final statuses = <String?>[];
    await _pump(tester, const ProductionScreen(), (r) async {
      if (r.url.path == '/api/staff/artisans') {
        return _json(200, {'items': [], 'total': 0});
      }
      statuses.add(r.url.queryParameters['status']);
      final filtered = r.url.queryParameters['status'] != null;
      return _json(200, {
        'items': filtered ? [] : [_job(1)],
        'total': filtered ? 0 : 1
      });
    });
    await tester.tap(find.byKey(const ValueKey('filter-status-all')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Completed').last);
    await tester.pumpAndSettle();
    expect(find.text('No jobs match these filters.'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Clear filters'));
    await tester.pumpAndSettle();
    expect(statuses.last, isNull);
    expect(find.textContaining('Batik 1'), findsOneWidget);
  });

  testWidgets('artisan user: no artisan filter, only progress action',
      (tester) async {
    final calls = <String>[];
    await _pump(tester, const ProductionScreen(), (r) async {
      calls.add('${r.method} ${r.url.path}');
      if (r.method == 'POST') {
        return _json(200, {..._job(1), 'progressPercent': 70});
      }
      if (r.url.path == '/api/production/jobs/1') return _json(200, _job(1));
      return _json(200, {'items': [_job(1)], 'total': 1});
    }, extra: [
      productionRoleProvider.overrideWithValue(AppRole.artisan),
    ]);
    expect(find.text('My jobs'), findsOneWidget);
    expect(find.byKey(const ValueKey('filter-artisan-all')), findsNothing);
    expect(calls.any((c) => c.contains('staff/artisans')), isFalse);
    await tester.tap(find.textContaining('Batik 1'));
    await tester.pumpAndSettle();
    expect(find.text('Assign artisan'), findsNothing);
    expect(find.text('Change status'), findsNothing);
    await tester.enterText(find.byKey(const ValueKey('progress-percent')), '101');
    await tester.tap(find.byKey(const ValueKey('progress-submit')));
    await tester.pumpAndSettle();
    expect(find.textContaining('0 to 100'), findsWidgets);
    await tester.enterText(find.byKey(const ValueKey('progress-percent')), '70');
    await tester.tap(find.byKey(const ValueKey('progress-submit')));
    await tester.pumpAndSettle();
    expect(calls, contains('POST /api/production/jobs/1/progress'));
  });

  testWidgets('staff status 409 shows current and requested', (tester) async {
    await _pump(tester, const ProductionScreen(), (r) async {
      if (r.url.path == '/api/staff/artisans') {
        return _json(200, {'items': [], 'total': 0});
      }
      if (r.method == 'POST') {
        return _json(409, {
          'error': {
            'code': 'invalid_transition',
            'message': 'bad',
            'details': [
              {'current': 'in_production', 'requested': 'quality_checking'}
            ]
          }
        });
      }
      if (r.url.path == '/api/production/jobs/1') return _json(200, _job(1));
      return _json(200, {'items': [_job(1)], 'total': 1});
    });
    await tester.tap(find.textContaining('Batik 1'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('move-quality_checking')));
    await tester.pumpAndSettle();
    expect(find.text('Cannot move from In production to Quality checking'),
        findsOneWidget);
  });
}
