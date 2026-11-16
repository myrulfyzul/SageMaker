import 'package:glados/glados.dart';
import 'package:sagemaker_flutter/app/role_permissions.dart';
import 'package:sagemaker_flutter/app/router.dart';
import 'package:sagemaker_flutter/app/shells/customer_shell.dart';
import 'package:sagemaker_flutter/features/auth/data/auth_user.dart';
import 'package:sagemaker_flutter/features/auth/state/session_provider.dart';

// Feature: sagemaker-asia-mobile-platform, Property 12: Role to navigation mapping
// **Validates: Requirements 6.10, 18.1, 19.1**

const _staffAll = [
  'Dashboard',
  'Orders',
  'Products',
  'Production',
  'More',
];
const _customerLabels = ['Home', 'Shop', 'Favourites', 'Cart', 'Profile'];

SessionSignedIn _session(AppRole role) =>
    SessionSignedIn(AuthUser(id: 1, name: 'U', email: 'u@x.my', role: role));

List<String> _expectedStaff(AppRole role) => switch (role) {
      AppRole.seller || AppRole.admin => _staffAll,
      AppRole.artisan => ['Production'],
      AppRole.customer => [],
    };

void main() {
  final cfg = ExploreConfig(numRuns: 100);

  Glados(any.choose(AppRole.values), cfg).test(
    'shown destinations equal the permitted set, in order, for any role',
    (role) {
      final labels =
          RolePermissions.staffDestinationsFor(role).map((d) => d.label);
      expect(labels.toList(), _expectedStaff(role));
      if (role == AppRole.customer) {
        expect(
          CustomerShell.customerDestinations.map((d) => d.label).toList(),
          _customerLabels,
        );
      }
    },
  );

  Glados2(any.choose(AppRole.values), any.choose(StaffDestination.values), cfg)
      .test('redirect allows exactly the permitted destinations', (role, dest) {
    final result =
        resolveRedirect(_session(role), Uri(path: dest.path));
    final permitted = RolePermissions.destinations[role]!.contains(dest);
    if (permitted) {
      expect(result, isNull);
    } else if (role.isStaff) {
      expect(result, RolePermissions.homePath(role));
    } else {
      expect(result, '/');
    }
  });

  Glados(any.choose(AppRole.values), cfg).test(
    'home path of a role is one of its own destinations',
    (role) {
      final home = RolePermissions.homePath(role);
      if (role.isStaff) {
        expect(
          RolePermissions.staffDestinationsFor(role).map((d) => d.path),
          contains(home),
        );
        expect(resolveRedirect(_session(role), Uri(path: home)), isNull);
      } else {
        expect(home, '/');
      }
    },
  );
}
