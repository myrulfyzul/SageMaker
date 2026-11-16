import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:sagemaker_flutter/core/network/api_client.dart';
import 'package:sagemaker_flutter/core/storage/preferences_provider.dart';
import 'package:sagemaker_flutter/features/about/ui/about_screen.dart';
import 'package:sagemaker_flutter/features/auth/data/auth_user.dart';
import 'package:sagemaker_flutter/features/auth/state/session_provider.dart';
import 'package:sagemaker_flutter/features/notifications/ui/notifications_screen.dart';
import 'package:sagemaker_flutter/features/profile/ui/profile_screen.dart';
import 'package:sagemaker_flutter/features/settings/ui/connection_settings_screen.dart';
import 'package:shared_preferences/shared_preferences.dart';

http.Response _json(int s, Object? b) => http.Response(jsonEncode(b), s,
    headers: {'content-type': 'application/json'});

class _SignedIn extends SessionNotifier {
  @override
  SessionState build() => const SessionSignedIn(
      AuthUser(id: 1, name: 'Aina', email: 'a@x.my', role: AppRole.customer));
}

Future<void> _pump(
  WidgetTester tester,
  Widget screen,
  Future<http.Response> Function(http.Request r) handler, {
  bool signedIn = true,
}) async {
  tester.view.physicalSize = const Size(800, 2400);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  SharedPreferences.setMockInitialValues({});
  final sp = await SharedPreferences.getInstance();
  await tester.pumpWidget(ProviderScope(
    overrides: [
      sharedPreferencesProvider.overrideWith((ref) async => sp),
      if (signedIn) sessionProvider.overrideWith(_SignedIn.new),
      apiClientProvider.overrideWithValue(ApiClient(
          baseUrl: 'http://t', client: MockClient(handler), token: 't')),
    ],
    child: MaterialApp(home: screen),
  ));
  await tester.pumpAndSettle();
}

Map<String, Object?> _note(int id, {bool read = false}) => {
      'id': id,
      'type': 'order',
      'title': 'Note $id',
      'body': 'Body $id',
      'isRead': read,
      'createdAt': '2025-06-01T03:04:05Z',
    };

void main() {
  group('Notifications', () {
    testWidgets('lists, shows 99+ badge, marks one and all read',
        (tester) async {
      var unread = 120;
      final calls = <String>[];
      await _pump(tester, const NotificationsScreen(), (r) async {
        calls.add('${r.method} ${r.url.path}');
        if (r.url.path == '/api/notifications') {
          return _json(200, {
            'items': [_note(1), _note(2, read: true)],
            'total': 2,
            'limit': 20,
            'offset': 0,
            'unreadCount': unread,
          });
        }
        unread = r.url.path.endsWith('read-all') ? 0 : 119;
        return _json(200, {'unreadCount': unread});
      });
      expect(find.text('99+'), findsOneWidget);
      expect(find.text('Note 1'), findsOneWidget);

      await tester.tap(find.text('Note 1'));
      await tester.pumpAndSettle();
      expect(calls, contains('POST /api/notifications/1/read'));
      expect(find.text('99+'), findsOneWidget);

      await tester.tap(find.text('Mark all read'));
      await tester.pumpAndSettle();
      expect(calls, contains('POST /api/notifications/read-all'));
      expect(find.text('99+'), findsNothing);
    });

    testWidgets('shows error with retry', (tester) async {
      var fail = true;
      await _pump(tester, const NotificationsScreen(), (r) async {
        if (fail) {
          return _json(500, {
            'error': {'message': 'boom'}
          });
        }
        return _json(200, {
          'items': [_note(1)],
          'total': 1,
          'unreadCount': 1
        });
      });
      expect(find.text('Server error'), findsOneWidget);
      fail = false;
      await tester.tap(find.text('Retry'));
      await tester.pumpAndSettle();
      expect(find.text('Note 1'), findsOneWidget);
    });
  });

  group('Profile', () {
    Future<http.Response> handler(http.Request r) async {
      if (r.url.path == '/api/me') {
        return _json(200, {
          'id': 1,
          'name': 'Aina',
          'email': 'a@x.my',
          'phone': '0123456789'
        });
      }
      if (r.url.path == '/api/me/addresses') {
        return _json(200, [
          {
            'id': 7,
            'recipientName': 'Aina',
            'phone': '0123456789',
            'line1': '1 Jalan Satu',
            'line2': null,
            'postcode': '50000',
            'city': 'KL',
            'state': 'Kuala Lumpur',
            'isDefault': true,
          }
        ]);
      }
      if (r.url.path == '/api/notifications') {
        return _json(200, {'items': [], 'total': 0, 'unreadCount': 150});
      }
      return _json(404, {});
    }

    testWidgets('shows profile, default address, links and badge',
        (tester) async {
      await _pump(tester, const ProfileScreen(), handler);
      expect(find.text('Aina'), findsWidgets);
      expect(find.text('Aina (Default)'), findsOneWidget);
      for (final p in [
        '/orders',
        '/custom-orders',
        '/notifications',
        '/about'
      ]) {
        expect(find.byKey(ValueKey('profile-link-$p')), findsOneWidget);
      }
      expect(find.text('99+'), findsOneWidget);
      expect(find.byKey(const ValueKey('profile-logout')), findsOneWidget);
    });

    testWidgets('invalid phone in the edit dialog is rejected locally',
        (tester) async {
      await _pump(tester, const ProfileScreen(), handler);
      await tester.tap(find.byKey(const ValueKey('profile-edit')));
      await tester.pumpAndSettle();
      await tester.enterText(find.byKey(const ValueKey('profile-phone')), '12');
      await tester.tap(find.text('Save'));
      await tester.pumpAndSettle();
      expect(find.text('Phone must be 8 to 15 digits'), findsOneWidget);
    });

    testWidgets('profile load failure shows retry', (tester) async {
      await _pump(
          tester,
          const ProfileScreen(),
          (r) async => _json(500, {
                'error': {'message': 'x'}
              }));
      expect(find.text('Retry'), findsWidgets);
    });

    testWidgets('signed out shows sign in, About and connection links only',
        (tester) async {
      await _pump(tester, const ProfileScreen(), handler, signedIn: false);
      expect(find.byKey(const ValueKey('profile-sign-in')), findsOneWidget);
      expect(find.byKey(const ValueKey('profile-logout')), findsNothing);
    });
  });

  testWidgets('About shows the prototype label without scrolling',
      (tester) async {
    await _pump(tester, const AboutScreen(), (r) async => _json(200, {}));
    expect(
        find.text(
            'Independent university prototype. Not officially Sagemaker.'),
        findsOneWidget);
  });

  group('Connection settings', () {
    testWidgets('rejects an invalid URL, saves a valid one, clears it',
        (tester) async {
      await _pump(tester, const ConnectionSettingsScreen(),
          (r) async => _json(200, {'status': 'ok'}));
      await tester.enterText(
          find.byKey(const ValueKey('url-field')), 'not a url');
      await tester.tap(find.byKey(const ValueKey('url-save')));
      await tester.pumpAndSettle();
      expect(find.text('Enter a valid http or https URL'), findsOneWidget);

      await tester.enterText(
          find.byKey(const ValueKey('url-field')), 'http://example.test:9000/');
      await tester.tap(find.byKey(const ValueKey('url-save')));
      await tester.pumpAndSettle();
      expect(find.text('http://example.test:9000'), findsOneWidget);

      await tester.tap(find.byKey(const ValueKey('url-clear')));
      await tester.pumpAndSettle();
      expect(find.text('http://example.test:9000'), findsNothing);
    });

    testWidgets('unreachable server shows the URL in use and retry',
        (tester) async {
      await _pump(tester, const ConnectionSettingsScreen(),
          (r) async => throw http.ClientException('down'));
      await tester.tap(find.byKey(const ValueKey('url-test')));
      await tester.pumpAndSettle();
      expect(find.byKey(const ValueKey('url-unreachable')), findsOneWidget);
      expect(find.textContaining('http://t'), findsOneWidget);
      expect(find.byKey(const ValueKey('url-retry')), findsOneWidget);
    });
  });
}
