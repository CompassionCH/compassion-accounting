In order to use Analytic Distribution, you must first set analytic tags
on the analytic accounts for which you want to dispatch the analytic lines.
Those tags will be used to create the rules.

The module comes with a CRON `Perform Analytic Distribution` that you can
enable to launch the attribution automatically when you want. It will
perform the distribution for the last fiscal year (closed period). One good
idea is to setup the CRON to launch at the beginning of your fiscal year.