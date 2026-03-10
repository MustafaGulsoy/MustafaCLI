/**
 * File Tree Component - Working Directory Browser
 * Standalone Angular 17 component
 */

import { Component, Input, Output, EventEmitter } from '@angular/core';
import { CommonModule } from '@angular/common';

export interface FileNode {
  name: string;
  path: string;
  isDirectory: boolean;
  children?: FileNode[];
}

interface TreeNode extends FileNode {
  expanded: boolean;
  children?: TreeNode[];
  depth: number;
}

@Component({
  selector: 'app-file-tree',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="file-tree">
      @for (node of treeNodes; track node.path) {
        <ng-container>
          <div
            class="tree-node"
            [style.padding-left.px]="node.depth * 20 + 8"
            [class.directory]="node.isDirectory"
            [class.selected]="selectedPath === node.path"
            (click)="onNodeClick(node)"
          >
            @if (node.isDirectory) {
              <span class="expand-icon">{{ node.expanded ? '\u25BE' : '\u25B8' }}</span>
            } @else {
              <span class="expand-icon spacer"></span>
            }
            <span class="file-icon">{{ getIcon(node) }}</span>
            <span class="node-name">{{ node.name }}</span>
          </div>
          @if (node.isDirectory && node.expanded && node.children) {
            @for (child of flattenChildren(node); track child.path) {
              <div
                class="tree-node"
                [style.padding-left.px]="child.depth * 20 + 8"
                [class.directory]="child.isDirectory"
                [class.selected]="selectedPath === child.path"
                (click)="onNodeClick(child)"
              >
                @if (child.isDirectory) {
                  <span class="expand-icon">{{ child.expanded ? '\u25BE' : '\u25B8' }}</span>
                } @else {
                  <span class="expand-icon spacer"></span>
                }
                <span class="file-icon">{{ getIcon(child) }}</span>
                <span class="node-name">{{ child.name }}</span>
              </div>
            }
          }
        </ng-container>
      }
      @if (treeNodes.length === 0) {
        <div class="empty-state">No files loaded</div>
      }
    </div>
  `,
  styles: [`
    .file-tree {
      font-family: 'Consolas', 'Monaco', monospace;
      font-size: 13px;
      overflow-y: auto;
      background: #1e1e1e;
      color: #cccccc;
      border-radius: 6px;
      padding: 4px 0;
      user-select: none;
    }

    .tree-node {
      display: flex;
      align-items: center;
      gap: 4px;
      padding: 3px 8px;
      cursor: pointer;
      white-space: nowrap;
    }

    .tree-node:hover {
      background: #2a2d2e;
    }

    .tree-node.selected {
      background: #094771;
    }

    .tree-node.directory .node-name {
      font-weight: 500;
    }

    .expand-icon {
      width: 16px;
      text-align: center;
      font-size: 12px;
      flex-shrink: 0;
      color: #888;
    }

    .expand-icon.spacer {
      visibility: hidden;
    }

    .file-icon {
      flex-shrink: 0;
      font-size: 14px;
    }

    .node-name {
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .empty-state {
      padding: 16px;
      text-align: center;
      color: #666;
      font-style: italic;
    }
  `]
})
export class FileTreeComponent {
  @Input() set files(value: FileNode[]) {
    this.treeNodes = this.buildTree(value, 0);
  }

  @Output() fileSelected = new EventEmitter<string>();

  treeNodes: TreeNode[] = [];
  selectedPath: string | null = null;
  private expandedPaths = new Set<string>();

  private buildTree(nodes: FileNode[], depth: number): TreeNode[] {
    if (!nodes) return [];

    return nodes
      .map(node => ({
        ...node,
        depth,
        expanded: this.expandedPaths.has(node.path),
        children: node.children
          ? this.buildTree(node.children, depth + 1)
          : undefined
      }))
      .sort((a, b) => {
        // Directories first, then alphabetical
        if (a.isDirectory !== b.isDirectory) {
          return a.isDirectory ? -1 : 1;
        }
        return a.name.localeCompare(b.name);
      });
  }

  onNodeClick(node: TreeNode): void {
    if (node.isDirectory) {
      node.expanded = !node.expanded;
      if (node.expanded) {
        this.expandedPaths.add(node.path);
      } else {
        this.expandedPaths.delete(node.path);
      }
    } else {
      this.selectedPath = node.path;
      this.fileSelected.emit(node.path);
    }
  }

  flattenChildren(node: TreeNode): TreeNode[] {
    const result: TreeNode[] = [];
    if (!node.children) return result;

    for (const child of node.children) {
      result.push(child);
      if (child.isDirectory && child.expanded && child.children) {
        result.push(...this.flattenChildren(child));
      }
    }
    return result;
  }

  getIcon(node: TreeNode): string {
    if (node.isDirectory) {
      return node.expanded ? '\uD83D\uDCC2' : '\uD83D\uDCC1';
    }

    const ext = node.name.split('.').pop()?.toLowerCase() || '';

    const iconMap: Record<string, string> = {
      'ts': '\uD83D\uDFE6',
      'js': '\uD83D\uDFE8',
      'py': '\uD83D\uDC0D',
      'json': '\u2699\uFE0F',
      'md': '\uD83D\uDCD6',
      'html': '\uD83C\uDF10',
      'css': '\uD83C\uDFA8',
      'scss': '\uD83C\uDFA8',
      'yaml': '\uD83D\uDCCB',
      'yml': '\uD83D\uDCCB',
      'toml': '\uD83D\uDCCB',
      'txt': '\uD83D\uDCC4',
      'sh': '\uD83D\uDCE6',
      'rs': '\uD83E\uDD80',
      'go': '\uD83D\uDC39',
      'java': '\u2615',
      'png': '\uD83D\uDDBC\uFE0F',
      'jpg': '\uD83D\uDDBC\uFE0F',
      'svg': '\uD83D\uDDBC\uFE0F',
      'gif': '\uD83D\uDDBC\uFE0F',
      'lock': '\uD83D\uDD12',
    };

    return iconMap[ext] || '\uD83D\uDCC4';
  }
}
