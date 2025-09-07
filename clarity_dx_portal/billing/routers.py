"""
Database router for separating user management from billing data
"""

class DatabaseRouter:
    """
    A router to control all database operations on models in the billing app
    """
    
    def db_for_read(self, model, **hints):
        """Point all read operations for billing models to 'monolith' database"""
        if model._meta.app_label == 'billing':
            return 'monolith'
        return None

    def db_for_write(self, model, **hints):
        """Point all write operations for billing models to 'monolith' database"""
        if model._meta.app_label == 'billing':
            return 'monolith'
        return None

    def allow_relation(self, obj1, obj2, **hints):
        """Allow relations if both models are in the billing app"""
        if obj1._meta.app_label == 'billing' and obj2._meta.app_label == 'billing':
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        """Ensure billing models are only migrated to the monolith database"""
        if app_label == 'billing':
            return db == 'monolith'
        elif db == 'monolith':
            return False
        return None
