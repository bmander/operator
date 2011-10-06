from django.core.management.base import BaseCommand, CommandError

class Command(BaseCommand):
    args = ''
    help = 'poll the MBTA'

    def handle(self, *args, **options):
        self.stdout.write( "success\n" )
