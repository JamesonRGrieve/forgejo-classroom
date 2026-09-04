// SPDX-License-Identifier: AGPL-3.0-or-later
'use client';

import type { ZephyrexClientExtension } from 'zephyrex';
import { AcceptPage } from './AcceptPage';
import { AssignmentDetailPage } from './AssignmentDetailPage';
import { ClassroomDetailPage } from './ClassroomDetailPage';
import { ClassroomsPage } from './ClassroomsPage';

function ClassroomSettings() {
  return (
    <section className="p-4" aria-labelledby="classroom-settings-heading">
      <h2 id="classroom-settings-heading" className="text-lg font-semibold">
        Classroom
      </h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Manage classrooms, rosters, assignments, and autograding for your Forgejo organization.
      </p>
    </section>
  );
}

export const classroomExtension: ZephyrexClientExtension = {
  name: 'classroom',
  displayName: 'Classroom',
  description: 'GitHub-Classroom-equivalent for Forgejo: classrooms, rosters, assignments, autograding.',
  serverExtension: 'classroom',
  pages: [
    { path: 'classroom', component: ClassroomsPage },
    { path: 'classroom/:classroomId', component: ClassroomDetailPage },
    { path: 'assignment/:assignmentId', component: AssignmentDetailPage },
    { path: 'accept/:assignmentId', component: AcceptPage },
  ],
  navItems: [{ title: 'Classrooms', url: '/classroom' }],
  settingsPanel: ClassroomSettings,
};
