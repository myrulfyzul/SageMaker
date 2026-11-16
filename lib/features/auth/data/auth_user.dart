/// Roles a signed-in user can have (Req 6).
enum AppRole {
  customer,
  seller,
  admin,
  artisan;

  /// Parses the backend role string. Unknown values are treated as customer
  /// so they never gain staff navigation.
  static AppRole parse(String? value) {
    switch (value) {
      case 'seller':
        return AppRole.seller;
      case 'admin':
        return AppRole.admin;
      case 'artisan':
        return AppRole.artisan;
      default:
        return AppRole.customer;
    }
  }

  bool get isStaff => this != AppRole.customer;
}

/// The signed-in user as returned by `/api/auth/login` and `/api/auth/session`.
class AuthUser {
  const AuthUser({
    required this.id,
    required this.name,
    required this.email,
    required this.role,
  });

  factory AuthUser.fromJson(Map<String, dynamic> json, {String? role}) {
    return AuthUser(
      id: (json['id'] as num?)?.toInt() ?? 0,
      name: (json['name'] ?? '').toString(),
      email: (json['email'] ?? '').toString(),
      role: AppRole.parse(role ?? json['role']?.toString()),
    );
  }

  final int id;
  final String name;
  final String email;
  final AppRole role;

  @override
  bool operator ==(Object other) =>
      other is AuthUser &&
      other.id == id &&
      other.name == name &&
      other.email == email &&
      other.role == role;

  @override
  int get hashCode => Object.hash(id, name, email, role);
}
