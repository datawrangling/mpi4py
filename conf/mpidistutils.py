# Author:  Lisandro Dalcin
# Contact: dalcinl@gmail.com

"""
Support for building mpi4py with distutils.
"""

# --------------------------------------------------------------------

# Environmental variables to look for configuration
MPICC_ENV  = ['MPICC']
MPICXX_ENV = ['MPICXX']
MPICFG_ENV = ['MPICFG']

# Default values to use for configuration
MPICC  = ['mpicc']
MPICXX = ['mpicxx', 'mpiCC', 'mpic++']
MPICFG = ('mpi', 'mpi.cfg')

# --------------------------------------------------------------------

import sys
if sys.version[:3] == '3.0':
    from distutils import version
    version.cmp = lambda a, b : (a > b) - (a < b)
    del version
del sys

# --------------------------------------------------------------------

import sys, os
from distutils import sysconfig
from distutils.spawn import find_executable
from distutils import log


def fix_any_flags(*flags):
    import re
    newflags = list(flags)
    if sys.platform == 'darwin':
        universal =  os.environ.get('MACOSX_UNIVERSAL_BUILD') or '1'
        if not int(universal):
            for i, flg in enumerate(flags):
                flg = re.sub('-arch\s+\w+\s', ' ', flg)
                flg = re.sub('-isysroot [^ \t]*', ' ', flg)
                newflags[i] = flg
    return newflags


def fix_linker_cmd(mpild, ldshared):
    if not ldshared: return mpild
    if (sys.platform.startswith('aix')
        and 'ld_so_aix' in ldshared):
        ldshared = ldshared.split(' ', 2)
    else:
        ldshared = ldshared.split(' ', 1)
    if len(ldshared) == 1: # just linker, no flags
        return mpild
    elif len(ldshared) == 2: # linker and flags
        return mpild + ' ' + ldshared[1]
    else: # assume using special linker script
        return  (ldshared[0] + ' '  +
                 mpild       + ' '  +
                 ldshared[2])


def customize_compiler(compiler,
                       mpicc=None, mpicxx=None,
                       environ=None):
    if environ is None:
        environ = os.environ
    if compiler.compiler_type == 'unix':
        # Core Python configuration
        (cc, cxx, cflags, ccshared, ldshared, so) = \
            sysconfig.get_config_vars('CC', 'CXX', 'CFLAGS',
                                      'CCSHARED', 'LDSHARED', 'SO')
        # Do any distutils flags fixup right now
        (cc, cxx, cflags, ccshared, ldshared, so) = \
            fix_any_flags(cc, cxx, cflags, ccshared, ldshared, so)
        # Compiler command overriding
        if mpicc:
            cc = mpicc
        if mpicxx:
            cxx = mpicxx
        if mpicc or mpicxx:
            mpild = mpicc or mpicxx
            ldshared = fix_linker_cmd(mpild, ldshared)
        # Environment handling
        cpp = os.environ.get('CPP') or (cc + ' -E')
        if 'LDFLAGS' in environ:
            ldshared = ldshared + ' ' + environ['LDFLAGS']
        if 'CFLAGS' in environ:
            cflags   = cflags   + ' ' + environ['CFLAGS']
            ldshared = ldshared + ' ' + environ['CFLAGS']
        if 'CPPFLAGS' in environ:
            cpp      = cpp      + ' ' + environ['CPPFLAGS']
            cflags   = cflags   + ' ' + environ['CPPFLAGS']
            ldshared = ldshared + ' ' + environ['CPPFLAGS']
        # Distutils compiler setup
        cc_cmd = cc + ' ' + cflags
        compiler.set_executables(
            preprocessor = cpp,
            compiler     = cc  + ' ' + cflags,
            compiler_so  = cc  + ' ' + cflags + ' ' + ccshared,
            compiler_cxx = cxx + ' ' + cflags + ' ' + ccshared,
            linker_so    = ldshared,
            linker_exe   = cc,
            )
        compiler.shared_lib_extension = so


def _find_mpi_compiler(envvars, executables, path=None):
    """
    Find MPI compilers in environment and path.
    """
    # search in environment
    if envvars:
        if isinstance(envvars, str):
            envvars = (envvars,)
        for var in envvars:
            cmd = os.environ.get(var)
            if cmd is not None: return cmd
    # search in path
    if executables:
        if isinstance(executables, str):
            executables = (executables,)
        for exe in executables:
            try:
                cmd, args = exe.split(' ', 1)
            except ValueError:
                cmd, args = exe, None
            cmd = find_executable(cmd, path)
            if cmd is not None:
                if args is not None:
                    cmd = cmd + ' ' + args
                return cmd
    # nothing found
    return None


# --------------------------------------------------------------------

try:
    from ConfigParser import ConfigParser
    from ConfigParser import Error as ConfigParserError
except ImportError:
    from configparser import ConfigParser
    from configparser import Error as ConfigParserError


def _config_parser(section, filenames, raw=False, vars=None):
    """
    Returns a dictionary of options obtained by parsing configuration
    files.
    """
    parser = ConfigParser()
    try:
        parser.read(filenames.split(os.path.pathsep))
    except ConfigParserError:
        log.error("error: parsing configuration file/s '%s'", filenames)
        return None
    if not parser.has_section(section):
        log.error("error: section '%s' not found "
                  "in configuration file/s '%s'", section, filenames)
        return None
    config_info = {}
    for k, v in parser.items(section, raw, vars):
        if k in ('define_macros',
                 'undef_macros',):
            config_info[k] = [m.strip() for m in v.split()]
        elif k in ('include_dirs',
                   'library_dirs',
                   'runtime_library_dirs',):
            pathsep = os.path.pathsep
            pathlist = [p.strip() for p in v.split(pathsep)]
            expanduser = os.path.expanduser
            expandvars = os.path.expandvars
            config_info[k] = [expanduser(expandvars(p))
                              for p in pathlist if p]
        elif k == 'libraries':
            config_info[k] = [l.strip() for l in v.split()]
        elif k in ('extra_compile_args',
                   'extra_link_args',
                   'extra_objects',):
            config_info[k] = [e.strip() for e in v.split()]
        else:
            config_info[k] = v.strip()
        #config_info[k] = v.replace('\\',' ').split()
    if 'define_macros' in config_info:
        macros = []
        for m in config_info['define_macros'] :
            try: # "-DFOO=blah"
                idx = m.index("=")
                macro = (m[:idx], m[idx+1:] or None)
            except ValueError: # bare "-DFOO"
                macro = (m, None)
            macros.append(macro)
        config_info['define_macros'] = macros
    return config_info


def _find_mpi_config(section, envvars=None, defaults=None):
    if not section and envvars:
        # look in environment
        if isinstance(envvars, str):
            envvars = (envvars,)
        for var in envvars:
            section = os.environ.get(var, None)
            if section: break
    filenames = ''
    if section and ',' in section:
        section, filenames = section.split(',', 1)
    if defaults:
        if not section:
            section = defaults[0]
        if not filenames:
            fname = defaults[1]
            if os.path.exists(fname):
                filenames = fname
    # parse configuraration
    if section and filenames:
        config_info = _config_parser(section, filenames)
        return section, filenames, config_info
    else:
        return section, filenames, None


def _configure(extension, confdict):
    if confdict is None: return
    for key, value in confdict.items():
        if hasattr(extension, key):
            item = getattr(extension, key)
            if type(item) is list:
                if type(value) is list:
                    for v in value:
                        if v not in item:
                            item.append(v)
                else:
                    if value not in item:
                        item.append(value)
            else:
                setattr(extension, key, value)

# --------------------------------------------------------------------

try:
    from mpiscanner import Scanner
except ImportError:
    try:
        from conf.mpiscanner import Scanner
    except ImportError:
        class Scanner(object):
            def parse_file(self, *args):
                raise NotImplementedError(
                    "You forgot to grab 'mpiscanner.py'")

class Configure(Scanner):
    SRCDIR = 'src'
    SOURCES = [os.path.join('include', 'mpi4py', 'mpi.pxi')]
    DESTDIR = os.path.join('src')
    CONFIG_H = 'config.h'
    MISSING_H = 'missing.h'
    def __init__(self):
        Scanner.__init__(self)
        for filename in self.SOURCES:
            fullname = os.path.join(self.SRCDIR, filename)
            self.parse_file(fullname)

    def write_headers(self, results, config_h=None, missing_h=None):
        if config_h is None:
            config_h = os.path.join(self.DESTDIR, self.CONFIG_H)
        if missing_h is None:
            missing_h = os.path.join(self.DESTDIR, self.MISSING_H)
        log.info("writing '%s'" % config_h)
        self.dump_config_h(config_h, results)
        log.info("writing '%s'" % missing_h)
        self.dump_missing_h(missing_h, None)

# --------------------------------------------------------------------

cmd_mpi_opts = [

    ('mpicxx=',  None,
     "MPI C++ compiler command, "
     "overrides environmental variables 'MPICXX' "
     "(defaults to 'mpicxx', 'mpiCC', or 'mpic++' if any is available)"),

    ('mpicc=',   None,
     "MPI C compiler command, "
     "overrides environmental variables 'MPICC' "
     "(defaults to 'mpicc' if available)"),

    ('mpi=',     None,
     "specify a configuration section, "
     "and an optional list of configuration files "
     + "(e.g. --mpi=section,file1" + os.path.pathsep + "file2), " +
     "to look for MPI includes/libraries, "
     "overrides environmental variables 'MPICFG' "
     "(defaults to section 'mpi' in configuration file 'mpi.cfg')"),

    ('configure', None,
     "exhaustive test for checking missing MPI constants/types/functions"),

    ]

def cmd_get_mpi_options(cmd_opts):
    optlist = []
    for (option, _, _) in cmd_opts:
        if option[-1] == "=":
            option = option[:-1]
        option = option.replace('-','_')
        optlist.append(option)
    return optlist


def cmd_initialize_mpi_options(self):
    mpiopts = cmd_get_mpi_options(cmd_mpi_opts)
    for op in mpiopts:
        setattr(self, op, None)

def cmd_set_undefined_mpi_options(self, basecmd):
    mpiopts = cmd_get_mpi_options(cmd_mpi_opts)
    optlist = tuple(zip(mpiopts, mpiopts))
    self.set_undefined_options(basecmd, *optlist)

# --------------------------------------------------------------------

from distutils.core import setup as fcn_setup
from distutils.core import Distribution as cls_Distribution
from distutils.extension import Extension as cls_Extension

from distutils.command import config as cmd_config
from distutils.command import build as cmd_build
from distutils.command import install as cmd_install
from distutils.command import clean as cmd_clean

from distutils.command import build_py as cmd_build_py
from distutils.command import build_ext as cmd_build_ext
from distutils.command import install_data as cmd_install_data
from distutils.command import install_lib as cmd_install_lib

from distutils.errors import DistutilsSetupError
from distutils.errors import DistutilsPlatformError
from distutils.errors import DistutilsOptionError

# --------------------------------------------------------------------

# Distribution class supporting a 'executables' keyword

class Distribution(cls_Distribution):

    def __init__ (self, attrs=None):
        # support for pkg data
        self.package_data = {}
        # PEP 314
        self.provides = None
        self.requires = None
        self.obsoletes = None
        # supports 'executables' keyword
        self.executables = None
        cls_Distribution.__init__(self, attrs)

    def has_executables(self):
        return self.executables and len(self.executables) > 0

# Extension class

class Extension(cls_Extension):
    pass

# Executable class

class Executable(Extension):
    pass

# setup function

def setup(**attrs):
    if 'distclass' not in attrs:
        attrs['distclass'] = Distribution
    if 'cmdclass' not in attrs:
        attrs['cmdclass'] = {}
    cmdclass = attrs['cmdclass']
    for cmd in (config, build, install, clean,
                build_py, build_ext, build_exe,
                install_data, install_exe,
                ):
        if cmd.__name__ not in cmdclass:
            cmdclass[cmd.__name__] = cmd
    return fcn_setup(**attrs)

# --------------------------------------------------------------------

# A minimalistic MPI program :-)

ConfigTest = """\
int main(int argc, char **argv) {
  MPI_Init(&argc,&argv);
  MPI_Finalize();
  return 0;
}
"""

class config(cmd_config.config):

    user_options = cmd_config.config.user_options + cmd_mpi_opts

    def initialize_options(self):
        cmd_config.config.initialize_options(self)
        self.noisy = 0
        cmd_initialize_mpi_options(self)

    def finalize_options(self):
        cmd_config.config.finalize_options(self)
        if not self.noisy:
            self.dump_source = 0

    def find_mpi_compiler(self, envvars, executables, path=None):
        return _find_mpi_compiler(envvars, executables, path)

    def run(self):
        # test configuration in specified section and file
        if self.mpi:
            sct, fn, cfg = _find_mpi_config(
                self.mpi, MPICFG_ENV, MPICFG)
            log.info("MPI configuration: "
                     "section '%s' from file/s '%s'", sct, fn)
            _configure(self, cfg)
        # test MPI C compiler
        mpicc = self.mpicc
        if mpicc is None:
            mpicc = self.find_mpi_compiler(MPICC_ENV, MPICC)
        log.info("MPI C compiler:    %s", mpicc  or 'not found')
        self.compiler = getattr(self.compiler, 'compiler_type',
                                self.compiler)
        self._check_compiler()
        customize_compiler(self.compiler, mpicc=mpicc, mpicxx=None)
        self.try_link(ConfigTest, headers=['mpi.h'], lang='c')
        # test MPI C++ compiler
        mpicxx = self.mpicxx
        if mpicxx is None:
            mpicxx = self.find_mpi_compiler(MPICXX_ENV, MPICXX)
        log.info("MPI C++ compiler:  %s", mpicxx or 'not found')
        if mpicxx:
            self.compiler = getattr(self.compiler, 'compiler_type',
                                    self.compiler)
            self._check_compiler()
            customize_compiler(self.compiler, mpicc=None, mpicxx=mpicxx)
            if self.compiler.compiler_type in ('unix', 'cygwin', 'mingw32'):
                self.compiler.compiler_so[0] = \
                    self.compiler.compiler_cxx[0]
                self.compiler.linker_exe[0]  = \
                    self.compiler.compiler_cxx[0]
            self.try_link(ConfigTest, headers=['mpi.h'], lang='c++')

    def run_configtests(self, compiler, config_info):
        self.compiler = compiler
        _configure(self, config_info)
        configure = Configure()
        results = []
        for name, code in configure.itertests():
            log.info("checking for '%s'" % name)
            ok = self.run_configtest(code)
            if not ok:
                log.info("**** failed check for %s" % name)
            results.append((name, ok))
        return configure.write_headers(results)

    def run_configtest(self, code, lang='c'):
        body = ['int main(int argc, char **argv) {',
                '  %s' % code,
                '  return 0;',
                '}']
        body = '\n'.join(body) + '\n'
        return self.try_link(body,
                             headers=['mpi.h'],
                             include_dirs=self.include_dirs,
                             libraries=self.libraries,
                             library_dirs=self.library_dirs,
                             lang=lang)

# --------------------------------------------------------------------

class build(cmd_build.build):

    user_options = cmd_build.build.user_options + cmd_mpi_opts

    def initialize_options(self):
        cmd_build.build.initialize_options(self)
        cmd_initialize_mpi_options(self)

    def finalize_options(self):
        cmd_build.build.finalize_options(self)
        config_cmd = self.get_finalized_command('config')
        if isinstance(config_cmd, config):
            cmd_set_undefined_mpi_options(self, 'config')

    def has_executables (self):
        return self.distribution.has_executables()

    sub_commands = \
        cmd_build.build.sub_commands + \
        [('build_exe', has_executables),
         ]

    # XXX disable build_exe subcommand !!!
    del sub_commands[-1]

# --------------------------------------------------------------------

class build_py(cmd_build_py.build_py):

    if sys.version[:3] < '2.4':

        def initialize_options(self):
            self.package_data = None
            cmd_build_py.build_py.initialize_options(self)

        def finalize_options (self):
            cmd_build_py.build_py.finalize_options(self)
            self.package_data = self.distribution.package_data
            self.data_files = self.get_data_files()

        def run(self):
            cmd_build_py.build_py.run(self)
            if self.packages:
                self.build_package_data()

        def get_data_files (self):
            """Generate list of '(package,src_dir,build_dir,filenames)' tuples"""
            data = []
            if not self.packages:
                return data
            for package in self.packages:
                # Locate package source directory
                src_dir = self.get_package_dir(package)

                # Compute package build directory
                build_dir = os.path.join(*([self.build_lib] + package.split('.')))

                # Length of path to strip from found files
                plen = len(src_dir)+1

                # Strip directory from globbed filenames
                filenames = [
                    file[plen:] for file in self.find_data_files(package, src_dir)
                    ]
                data.append((package, src_dir, build_dir, filenames))
            return data

        def find_data_files (self, package, src_dir):
            """Return filenames for package's data files in 'src_dir'"""
            from glob import glob
            from distutils.util import convert_path
            globs = (self.package_data.get('', [])
                     + self.package_data.get(package, []))
            files = []
            for pattern in globs:
                # Each pattern has to be converted to a platform-specific path
                filelist = glob(os.path.join(src_dir, convert_path(pattern)))
                # Files that match more than one pattern are only added once
                files.extend([fn for fn in filelist if fn not in files])
            return files

        def get_package_dir (self, package):
            """Return the directory, relative to the top of the source
               distribution, where package 'package' should be found
               (at least according to the 'package_dir' option, if any)."""
            import string
            path = string.split(package, '.')

            if not self.package_dir:
                if path:
                    return apply(os.path.join, path)
                else:
                    return ''
            else:
                tail = []
                while path:
                    try:
                        pdir = self.package_dir[string.join(path, '.')]
                    except KeyError:
                        tail.insert(0, path[-1])
                        del path[-1]
                    else:
                        tail.insert(0, pdir)
                        return apply(os.path.join, tail)
                else:
                    pdir = self.package_dir.get('')
                    if pdir is not None:
                        tail.insert(0, pdir)

                    if tail:
                        return apply(os.path.join, tail)
                    else:
                        return ''

        def build_package_data (self):
            """Copy data files into build directory"""
            lastdir = None
            for package, src_dir, build_dir, filenames in self.data_files:
                for filename in filenames:
                    target = os.path.join(build_dir, filename)
                    self.mkpath(os.path.dirname(target))
                    self.copy_file(os.path.join(src_dir, filename), target,
                                   preserve_mode=False)

# --------------------------------------------------------------------

class build_ext(cmd_build_ext.build_ext):

    user_options = cmd_build_ext.build_ext.user_options + cmd_mpi_opts

    def initialize_options(self):
        cmd_build_ext.build_ext.initialize_options(self)
        cmd_initialize_mpi_options(self)

    def finalize_options(self):
        cmd_build_ext.build_ext.finalize_options(self)
        import sys, os
        if (sys.platform.startswith('linux') or \
            sys.platform.startswith('gnu')) and \
            sysconfig.get_config_var('Py_ENABLE_SHARED'):
            try:
                py_version = sysconfig.get_python_version()
                bad_pylib_dir = os.path.join(sys.prefix, "lib",
                                             "python" + py_version,
                                             "config")
                self.library_dirs.remove(bad_pylib_dir)
            except ValueError:
                pass
            pylib_dir = sysconfig.get_config_var("LIBDIR")
            if pylib_dir not in self.library_dirs:
                self.library_dirs.append(pylib_dir)
        build_cmd = self.get_finalized_command('build')
        if isinstance(build_cmd,  build):
            cmd_set_undefined_mpi_options(self, 'build')

    def build_extensions(self):
        # First, sanity-check the 'extensions' list
        self.check_extensions_list(self.extensions)
        # parse configuration file and  configure compiler
        config_info = self.configure_extensions()
        mpicc = mpicxx = None
        if config_info:
            mpicc  = config_info.get('mpicc')
            mpicxx = config_info.get('mpicxx')
        compiler = self.configure_compiler(mpicc=mpicc, mpicxx=mpicxx)
        # extra configuration, MPI 2 features
        if self.configure:
            log.info('testing for missing MPI-2 features')
            config_cmd = self.get_finalized_command('config')
            config_cmd.run_configtests(compiler, config_info)
            macro = 'PyMPI_HAVE_CONFIG_H'
            self.compiler.define_macro(macro, None)
            log.info("defining preprocessor macro '%s'" % macro)
        # and finally build extensions
        for ext in self.extensions:
            self.build_extension(ext)

    def configure_compiler(self, mpicc=None, mpicxx=None, compiler=None):
        #
        mpicc = self.mpicc or mpicc
        if mpicc is None:
            mpicc = self.find_mpi_compiler(MPICC_ENV, MPICC)
        log.info("MPI C compiler:    %s", mpicc  or 'not found')
        #
        mpicxx = self.mpicxx or mpicxx
        if mpicxx is None:
            mpicxx = self.find_mpi_compiler(MPICXX_ENV, MPICXX)
        log.info("MPI C++ compiler:  %s", mpicxx or 'not found')
        #
        if compiler is None: compiler = self.compiler
        customize_compiler(compiler, mpicc=mpicc, mpicxx=mpicxx)
        return compiler

    def find_mpi_compiler(self, envvars, executables, path=None):
        return _find_mpi_compiler(envvars, executables, path)

    def configure_extensions(self):
        config_info = self.find_mpi_config(
            self.mpi, MPICFG_ENV, MPICFG)
        if config_info:
            for ext in self.extensions:
                self.configure_extension(ext, config_info)
        return config_info

    def find_mpi_config(self, section, envvars=None, defaults=None):
        # parse configuration file
        sect, fnames, cfg_info = _find_mpi_config(
            section, envvars, defaults)
        if cfg_info:
            log.info("MPI configuration: "
                     "from section '%s' in file/s '%s'", sect, fnames)
        return cfg_info

    def configure_extension(self, extension, config_info):
        _configure(extension, config_info)


# --------------------------------------------------------

# Command class to build executables

class build_exe(build_ext):

    description = "build binary executable components"

    user_options = [
        ('build-exe=', None,
         "build directory for executable components"),
        ] + build_ext.user_options


    def initialize_options (self):
        build_ext.initialize_options(self)
        self.build_base = None
        self.build_exe  = None

    def finalize_options (self):
        build_ext.finalize_options(self)
        self.configure = None
        self.set_undefined_options('build',
                                   ('build_base','build_base'))
        from distutils.util import get_platform
        plat_specifier = ".%s-%s" % (get_platform(), sys.version[0:3])
        if hasattr(sys, 'gettotalrefcount') and sys.version[0:3] > '2.5':
            plat_specifier += '-pydebug'
        if self.build_exe is None:
            self.build_exe = os.path.join(self.build_base,
                                          'exe' + plat_specifier)
        self.executables = self.distribution.executables
        # a bit of hack
        self.extensions  = self.distribution.executables
        self.check_extensions_list = self.check_executables_list
        self.build_extension = self.build_executable

    def check_executables_list (self, executables):
        ListType = type([])
        if type(executables) is not ListType:
            raise DistutilsSetupError(
                "'executables' option must be a list of Executable instances")
        for exe in executables:
            if not isinstance(exe, Executable):
                raise DistutilsSetupError(
                    "'executables' items must be Executable instances")

    def get_outputs (self):
        exe_ext = sysconfig.get_config_var('EXE') or ''
        if exe_ext: exe_ext = os.path.extsep + exe_ext
        outputs = []
        for exe in self.executables:
            exe_filename = os.path.join(self.build_exe, exe.name) + exe_ext
            outputs.append(exe_filename)
        return outputs

    def build_executable (self, exe):
        ListType, TupleType = type([]), type(())
        from distutils.dep_util import newer_group
        sources = exe.sources
        if sources is None or type(sources) not in (ListType, TupleType):
            raise DistutilsSetupError(
                ("in 'executables' option (executable '%s'), " +
                 "'sources' must be present and must be " +
                 "a list of source filenames") % exe.name
                )
        sources = list(sources)
        exe_filename = os.path.join(self.build_exe, exe.name)
        depends = sources + exe.depends
        if not (self.force or newer_group(depends, exe_filename, 'newer')):
            log.debug("skipping '%s' executable (up-to-date)", exe.name)
            return
        else:
            log.info("building '%s' executable", exe.name)

        # Next, compile the source code to object files.

        # XXX not honouring 'define_macros' or 'undef_macros' -- the
        # CCompiler API needs to change to accommodate this, and I
        # want to do one thing at a time!

        macros = exe.define_macros[:]
        for undef in exe.undef_macros:
            macros.append((undef,))

        # Two possible sources for extra compiler arguments:
        #   - 'extra_compile_args' in Extension object
        #   - CFLAGS environment variable (not particularly
        #     elegant, but people seem to expect it and I
        #     guess it's useful)
        # The environment variable should take precedence, and
        # any sensible compiler will give precedence to later
        # command line args.  Hence we combine them in order:
        extra_args = exe.extra_compile_args or []
        extra_args = extra_args[:]

        objects = self.compiler.compile(sources,
                                        output_dir=self.build_temp,
                                        macros=macros,
                                        include_dirs=exe.include_dirs,
                                        debug=self.debug,
                                        extra_postargs=extra_args,
                                        depends=exe.depends)

        # XXX -- this is a Vile HACK!
        #
        # The setup.py script for Python on Unix needs to be able to
        # get this list so it can perform all the clean up needed to
        # avoid keeping object files around when cleaning out a failed
        # build of an extension module.  Since Distutils does not
        # track dependencies, we have to get rid of intermediates to
        # ensure all the intermediates will be properly re-built.
        #
        self._built_objects = objects[:]

        # XXX -- this is a Vile HACK!
        #
        # Remove msvcrXX.dll when building executables with MinGW
        #
        if self.compiler.compiler_type == 'mingw32':
            try: del self.compiler.dll_libraries[:]
            except: pass

        # Now link the object files together into a "shared object" --
        # of course, first we have to figure out all the other things
        # that go into the mix.
        if exe.extra_objects:
            objects.extend(exe.extra_objects)
        extra_args = exe.extra_link_args or []
        extra_args = extra_args[:]
        # Get special linker flags for building a executable with
        # bundled Python library, also fix location of needed
        # python.exp file on AIX
        ldshflag = sysconfig.get_config_var('LINKFORSHARED') or ''
        if sys.platform.startswith('aix'):
            python_lib = sysconfig.get_python_lib(standard_lib=1)
            python_exp = os.path.join(python_lib, 'config', 'python.exp')
            ldshflag = ldshflag.replace('Modules/python.exp', python_exp)
        extra_args.extend(ldshflag.split())
        # Detect target language, if not provided
        language = exe.language or self.compiler.detect_language(sources)
        self.compiler.link_executable(
            objects, exe_filename,
            output_dir=None,
            libraries=self.get_libraries(exe),
            library_dirs=exe.library_dirs,
            runtime_library_dirs=exe.runtime_library_dirs,
            extra_preargs=None,
            extra_postargs=extra_args,
            debug=self.debug,
            target_lang=language)

# --------------------------------------------------------------------

class install(cmd_install.install):

    def has_exe (self):
        return self.distribution.has_executables()

    sub_commands = \
        cmd_install.install.sub_commands[:] + \
        [('install_exe', has_exe),
         ]

    # XXX disable install_exe subcommand !!!
    del sub_commands[-1]

# --------------------------------------------------------------------

class install_data (cmd_install_data.install_data):

    def finalize_options (self):
        self.set_undefined_options('install',
                                   ('install_lib', 'install_dir'),
                                   ('root', 'root'),
                                   ('force', 'force'),
                                   )

# --------------------------------------------------------------------

class install_exe(cmd_install_lib.install_lib):

    description = "install binary executable components"

    user_options = [
        ('install-dir=', 'd', "directory to install to"),
        ('build-dir=','b', "build directory (where to install from)"),
        ('force', 'f', "force installation (overwrite existing files)"),
        ('skip-build', None, "skip the build steps"),
        ]

    boolean_options = ['force', 'skip-build']
    negative_opt = { }

    def initialize_options (self):
        self.install_dir = None
        self.build_dir = None
        self.force = 0
        self.skip_build = None

    def finalize_options (self):
        self.set_undefined_options('build_exe',
                                   ('build_exe', 'build_dir'))
        self.set_undefined_options('install',
                                   ('force', 'force'),
                                   ('skip_build', 'skip_build'),
                                   ('install_scripts', 'install_dir'))

    def run (self):
        self.build()
        self.install()

    def build (self):
        if not self.skip_build:
            if self.distribution.has_executables():
                self.run_command('build_exe')

    def install (self):
        if os.path.isdir(self.build_dir):
            self.outfiles = self.copy_tree(self.build_dir, self.install_dir)
        else:
            self.warn("'%s' does not exist -- no executables to install" %
                      self.build_dir)
            self.outfiles = None

    def get_outputs (self):
        return self.outfiles

    def get_inputs (self):
        inputs = []
        if self.distribution.has_executables():
            build_exe = self.get_finalized_command('build_exe')
            inputs.extend(build_exe.get_outputs())
        return inputs

# --------------------------------------------------------------------

class clean(cmd_clean.clean):

    description = "clean up temporary files from 'build' command"
    user_options = \
        cmd_clean.clean.user_options[:2] + [
        ('build-exe=', None,
         "build directory for executable components "
         "(default: 'build_exe.build-exe')"),
        ] + cmd_clean.clean.user_options[2:]

    def initialize_options(self):
        cmd_clean.clean.initialize_options(self)
        self.build_exe  = None

    def finalize_options(self):
        cmd_clean.clean.finalize_options(self)
        self.set_undefined_options('build_exe',
                                   ('build_exe', 'build_exe'))

    def run(self):
        from distutils.dir_util import remove_tree
        # remove the build/temp.<plat> directory
        # (unless it's already gone)
        if os.path.exists(self.build_temp):
            remove_tree(self.build_temp, dry_run=self.dry_run)
        else:
            log.debug("'%s' does not exist -- can't clean it",
                      self.build_temp)

        if self.all:
            # remove build directories
            for directory in (self.build_lib,
                              self.build_exe,
                              self.bdist_base,
                              self.build_scripts):
                if os.path.exists(directory):
                    remove_tree(directory, dry_run=self.dry_run)
                else:
                    log.debug("'%s' does not exist -- can't clean it",
                              directory)

        # just for the heck of it, try to remove the base build directory:
        # we might have emptied it right now, but if not we don't care
        if not self.dry_run:
            try:
                os.rmdir(self.build_base)
                log.info("removing '%s'", self.build_base)
            except OSError:
                pass

# --------------------------------------------------------------------
