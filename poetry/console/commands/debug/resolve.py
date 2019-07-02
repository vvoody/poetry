import re

from typing import List

from cleo import argument
from cleo import option

from ..command import Command


class DebugResolveCommand(Command):

    name = "resolve"
    description = "Debugs dependency resolution."

    arguments = [
        argument("package", "Packages to resolve.", optional=True, multiple=True)
    ]
    options = [
        option(
            "extras",
            "E",
            "Extras to activate for the dependency.",
            flag=False,
            multiple=True,
        ),
        option("python", None, "Python version(s) to use for resolution.", flag=False),
        option("tree", None, "Displays the dependency tree."),
        option("install", None, "Show what would be installed for the current system."),
    ]

    loggers = ["poetry.repositories.pypi_repository"]

    def handle(self):
        from poetry.packages import ProjectPackage
        from poetry.puzzle import Solver
        from poetry.repositories.repository import Repository
        from poetry.semver import parse_constraint
        from poetry.utils.env import EnvManager

        packages = self.argument("package")

        if not packages:
            package = self.poetry.package
        else:
            package = ProjectPackage(
                self.poetry.package.name, self.poetry.package.version
            )
            requirements = self._format_requirements(packages)

            for name, constraint in requirements.items():
                dep = package.add_dependency(name, constraint)
                extras = []
                for extra in self.option("extras"):
                    if " " in extra:
                        extras += [e.strip() for e in extra.split(" ")]
                    else:
                        extras.append(extra)

                for ex in extras:
                    dep.extras.append(ex)

        package.python_versions = self.option("python") or (
            self.poetry.package.python_versions
        )

        pool = self.poetry.pool

        solver = Solver(package, pool, Repository(), Repository(), self._io)

        ops = solver.solve()

        self.line("")
        self.line("Resolution results:")
        self.line("")

        if self.option("tree"):
            show_command = self.application.find("show")
            show_command.init_styles(self.io)

            packages = [op.package for op in ops]
            repo = Repository(packages)

            requires = package.requires + package.dev_requires
            for pkg in repo.packages:
                for require in requires:
                    if pkg.name == require.name:
                        show_command.display_package_tree(self.io, pkg, repo)
                        break

            return 0

        env = EnvManager(self.poetry.config).get(self.poetry.file.parent)
        current_python_version = parse_constraint(
            ".".join(str(v) for v in env.version_info)
        )
        for op in ops:
            pkg = op.package
            if self.option("install"):
                if not pkg.python_constraint.allows(
                    current_python_version
                ) or not env.is_valid_for_marker(pkg.marker):
                    continue

            self.line(
                "  - <info>{}</info> (<comment>{}</comment>)".format(
                    pkg.name, pkg.version
                )
            )
            if not pkg.python_constraint.is_any():
                self.line("    - python: {}".format(pkg.python_versions))

            if not pkg.marker.is_any():
                self.line("    - marker: {}".format(pkg.marker))

    def _determine_requirements(self, requires):  # type: (List[str]) -> List[str]
        from poetry.semver import parse_constraint

        if not requires:
            return []

        requires = self._parse_name_version_pairs(requires)
        for requirement in requires:
            if "version" in requirement:
                parse_constraint(requirement["version"])

        return requires

    def _parse_name_version_pairs(self, pairs):  # type: (list) -> list
        result = []

        for i in range(len(pairs)):
            if pairs[i].startswith("git+https://"):
                url = pairs[i].lstrip("git+")
                rev = None
                if "@" in url:
                    url, rev = url.split("@")

                pair = {"name": url.split("/")[-1].rstrip(".git"), "git": url}
                if rev:
                    pair["rev"] = rev

                result.append(pair)

                continue

            pair = re.sub("^([^=: ]+)[=: ](.*)$", "\\1 \\2", pairs[i].strip())
            pair = pair.strip()

            if " " in pair:
                name, version = pair.split(" ", 2)
                result.append({"name": name, "version": version})
            else:
                result.append({"name": pair, "version": "*"})

        return result

    def _format_requirements(self, requirements):  # type: (List[str]) -> dict
        requires = {}
        requirements = self._determine_requirements(requirements)

        for requirement in requirements:
            name = requirement.pop("name")
            requires[name] = requirement

        return requires
