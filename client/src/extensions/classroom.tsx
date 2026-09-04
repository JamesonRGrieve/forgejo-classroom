// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';

import type { ZephyrexClientExtension } from 'zephyrex';

function ClassroomDashboard() {
  return (
    <section className="p-6" aria-labelledby="classroom-heading">
      <h1 id="classroom-heading" className="text-2xl font-bold mb-4">
        Classrooms
      </h1>
      <p className="text-muted-foreground">
        Manage classrooms, rosters, assignments, and autograding for your Forgejo
        organization. Assignments clone a template repository per student or group;
        pushes are graded by Forgejo Actions and scores appear here.
      </p>
    </section>
  );
}

function ClassroomSettings() {
  return (
    <section className="p-4" aria-labelledby="classroom-settings-heading">
      <h2 id="classroom-settings-heading" className="text-lg font-semibold mb-2">
        Classroom Settings
      </h2>
      <p className="text-muted-foreground">
        Configure the linked Forgejo organization, autograding defaults, and roster
        import.
      </p>
    </section>
  );
}

export const classroomExtension: ZephyrexClientExtension = {
  name: 'classroom',
  displayName: 'Classroom',
  description: 'Classrooms, rosters, assignments, and autograding for Forgejo',
  serverExtension: 'classroom',
  pages: [
    {
      path: 'classroom',
      component: ClassroomDashboard,
    },
  ],
  navItems: [
    {
      title: 'Classrooms',
      url: '/classroom',
    },
  ],
  settingsPanel: ClassroomSettings,
};
